from decimal import Decimal

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import (
    Account,
    Address,
    Cart,
    Category,
    Customer,
    Product,
    ProductVariant,
    SellerOrder,
    Seller,
    Style,
    set_customer_styles,
    set_product_styles,
)


class RegistrationForm(UserCreationForm):
    email = forms.EmailField()

    class Meta:
        model = Account
        fields = ["username", "email", "password1", "password2"]

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if Account.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is already in use.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if Account.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("This email address is already in use.")
        return email

    @transaction.atomic
    def save(self, commit=True):
        account = super().save(commit=False)
        account.role = "CUSTOMER"
        if commit:
            account.save()
            customer = Customer.objects.create(account=account)
            Cart.objects.create(customer=customer)
        return account


class SellerRegistrationForm(RegistrationForm):
    store_name = forms.CharField(max_length=120)
    store_description = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}))
    contact_email = forms.EmailField()

    def clean_store_name(self):
        name = " ".join(self.cleaned_data["store_name"].split())
        if Seller.objects.filter(store_name__iexact=name).exists():
            raise forms.ValidationError("This store name is already in use.")
        return name

    @transaction.atomic
    def save(self, commit=True):
        # A seller needs a store instead of a customer profile and cart.
        account = UserCreationForm.save(self, commit=False)
        account.role = "SELLER"
        if commit:
            account.save()
            Seller.objects.create(
                account=account,
                store_name=self.cleaned_data["store_name"],
                store_description=self.cleaned_data["store_description"],
                email=self.cleaned_data["contact_email"],
                approval_status="PENDING",
            )
        return account


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ["email"]

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if (
            Account.objects.filter(email__iexact=email)
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise forms.ValidationError("This email address is already in use.")
        return email

    def save(self, commit=True):
        account = super().save(commit=False)
        if commit:
            account.save(update_fields=["email"])
        return account


class ProfileForm(forms.ModelForm):
    styles = forms.ModelMultipleChoiceField(
        queryset=Style.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Customer
        fields = ["gender", "height", "weight", "styles"]
        labels = {"height": "Height (cm)", "weight": "Weight (kg)"}
        help_texts = {
            "gender": "Optional. You can change or clear this preference at any time.",
            "height": "Supported demo range: 140–210 cm. Optional.",
            "weight": "Supported demo range: 35–160 kg. Optional.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["styles"] = self.instance.get_styles()

    @transaction.atomic
    def save(self, commit=True):
        customer = super().save(commit=False)
        if commit:
            customer.save()
            set_customer_styles(customer, self.cleaned_data["styles"])
        return customer


class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ["recipient_name", "phone_number", "address_line", "postal_code"]
        labels = {
            "address_line": "Street address and unit number",
            "postal_code": "Singapore postal code",
        }
        widgets = {"address_line": forms.Textarea(attrs={"rows": 3})}


class VariantSelectionForm(forms.Form):
    size = forms.CharField(max_length=12)
    colour = forms.CharField(max_length=40)
    quantity = forms.IntegerField(min_value=1, max_value=10000)


class QuantityForm(forms.Form):
    # The bag checks this quantity against the item's current stock.
    quantity = forms.IntegerField(min_value=1)


class StoreProfileForm(forms.ModelForm):
    class Meta:
        model = Seller
        fields = ["store_name", "store_description", "email"]
        labels = {"email": "Store contact email"}
        widgets = {"store_description": forms.Textarea(attrs={"rows": 4})}

    def clean_store_name(self):
        name = " ".join(self.cleaned_data["store_name"].split())
        if (
            Seller.objects.filter(store_name__iexact=name)
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise ValidationError("This store name is already in use.")
        return name

    def save(self, commit=True):
        seller = super().save(commit=False)
        if commit:
            if seller.pk:
                seller.save(update_fields=["store_name", "store_description", "email"])
            else:
                seller.save()
        return seller


class StaffSellerForm(StoreProfileForm):
    commission_percent = forms.DecimalField(
        label="Commission (%)",
        min_value=0,
        max_value=100,
        decimal_places=2,
        max_digits=5,
        help_text="10 means 10%. Applies to future purchases only.",
    )

    class Meta(StoreProfileForm.Meta):
        fields = StoreProfileForm.Meta.fields + ["commission_percent"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["commission_percent"].initial = self.instance.commission_rate * 100

    def save(self, commit=True):
        seller = super().save(commit=False)
        seller.commission_rate = self.cleaned_data["commission_percent"] / Decimal(
            "100"
        )
        if commit:
            if seller.pk:
                seller.save(
                    update_fields=[
                        "store_name",
                        "store_description",
                        "email",
                        "commission_rate",
                    ]
                )
            else:
                seller.save()
        return seller


class StaffSellerCreateForm(StaffSellerForm):
    username = forms.CharField(max_length=150)
    account_email = forms.EmailField(label="Account email")
    password = forms.CharField(
        widget=forms.PasswordInput,
        help_text="At least 8 characters; avoid common passwords.",
    )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if Account.objects.filter(username__iexact=username).exists():
            raise ValidationError("This username is already in use.")
        Account._meta.get_field("username").run_validators(username)
        return username

    def clean_account_email(self):
        email = self.cleaned_data["account_email"].strip().lower()
        if Account.objects.filter(email__iexact=email).exists():
            raise ValidationError("This email address is already in use.")
        return email

    def clean(self):
        values = super().clean()
        if values.get("password"):
            user = Account(
                username=values.get("username", ""),
                email=values.get("account_email", ""),
            )
            try:
                validate_password(values["password"], user)
            except ValidationError as error:
                self.add_error("password", error)
        return values


class ProductForm(forms.ModelForm):
    styles = forms.ModelMultipleChoiceField(
        queryset=Style.objects.all(), required=True, widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        model = Product
        fields = [
            "name",
            "description",
            "category",
            "collection",
            "price",
            "image",
            "styles",
        ]
        labels = {
            "price": "Price (SGD)", "image": "Primary image",
            "collection": "Clothing collection",
        }
        widgets = {"description": forms.Textarea(attrs={"rows": 6})}
        help_texts = {
            "collection": "Choose the garment's intended collection. Use Unisex for clothing intended for everyone.",
            "image": "JPEG, PNG or WebP, up to 5 MB. Leave blank to keep the current image.",
            "description": (
                "Include the materials, care instructions and size guidance supplied by your store."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["styles"] = self.instance.get_styles()

    def save_styles(self, product):
        set_product_styles(product, self.cleaned_data["styles"])

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image and hasattr(image, "content_type"):
            if image.size > 5 * 1024 * 1024:
                raise ValidationError("Choose an image no larger than 5 MB.")
            # Django's ImageField has already checked and opened this upload.
            if image.image.format not in ["JPEG", "PNG", "WEBP"]:
                raise ValidationError("Choose a valid JPEG, PNG or WebP image.")
        return image


class StaffProductCreateForm(ProductForm):
    seller = forms.ModelChoiceField(
        queryset=Seller.objects.select_related("account").all()
    )

    class Meta(ProductForm.Meta):
        fields = ["seller"] + ProductForm.Meta.fields


class VariantForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = ["size", "colour", "sku", "stock_quantity"]
        labels = {"stock_quantity": "Initial stock quantity"}

    def __init__(self, *args, product=None, **kwargs):
        super().__init__(*args, **kwargs)
        if product:
            self.instance.product = product
        if self.instance.pk:
            self.fields.pop("stock_quantity")
            if self.instance.cart_items.exists() or self.instance.order_items.exists():
                for field in ["size", "colour", "sku"]:
                    self.fields[field].disabled = True
                    self.fields[field].help_text = (
                        "Identity is locked because a bag or order references this variant."
                    )

    def clean_size(self):
        return self.cleaned_data["size"].strip().upper()

    def clean_colour(self):
        return " ".join(self.cleaned_data["colour"].split()).title()

    def clean_sku(self):
        return self.cleaned_data["sku"].strip().upper()

    def clean(self):
        values = super().clean()
        if values.get("size") and values.get("colour"):
            duplicates = ProductVariant.objects.filter(
                product=self.instance.product,
                size__iexact=values["size"],
                colour__iexact=values["colour"],
            ).exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise ValidationError(
                    "This product already has this size and colour combination."
                )
        return values


class InventoryAdjustmentForm(forms.Form):
    delta = forms.IntegerField(
        label="Stock adjustment",
        min_value=-100000,
        max_value=100000,
        help_text="Use a positive number to add units or a negative number to remove units.",
    )

    def clean_delta(self):
        value = self.cleaned_data["delta"]
        if value == 0:
            raise ValidationError("Enter an adjustment other than zero.")
        return value


class TaxonomyForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name"]

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if (
            self._meta.model.objects.filter(name__iexact=name)
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise ValidationError("This name already exists.")
        return name


class StyleForm(TaxonomyForm):
    class Meta(TaxonomyForm.Meta):
        model = Style
        fields = ["name", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class ReportFilterForm(forms.Form):
    seller = forms.ModelChoiceField(
        queryset=Seller.objects.all(), required=False, empty_label="All retailers"
    )
    status = forms.ChoiceField(
        required=False,
        choices=[("", "All fulfilment states")] + list(SellerOrder.STATUS_CHOICES),
    )
    start = forms.DateField(
        label="Placed from",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    end = forms.DateField(
        label="Placed through",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def clean(self):
        values = super().clean()
        if (
            values.get("start")
            and values.get("end")
            and values["start"] > values["end"]
        ):
            raise ValidationError(
                "The start date must be before or equal to the end date."
            )
        return values
