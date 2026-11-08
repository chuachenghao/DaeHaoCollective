import django.contrib.auth.validators
import django.core.validators
import django.db.models.deletion
import django.db.models.functions.text
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Account',
            fields=[
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('accountID', models.BigAutoField(primary_key=True, serialize=False)),
                ('username', models.CharField(max_length=150, unique=True, validators=[django.contrib.auth.validators.UnicodeUsernameValidator()])),
                ('email', models.EmailField(max_length=254, unique=True)),
                ('role', models.CharField(choices=[('CUSTOMER', 'Customer'), ('SELLER', 'Seller'), ('ADMIN', 'Administrator')], default='CUSTOMER', max_length=10)),
            ],
            options={
                'constraints': [models.UniqueConstraint(django.db.models.functions.text.Lower('email'), name='unique_account_email_lower'), models.UniqueConstraint(django.db.models.functions.text.Lower('username'), name='unique_username_lower')],
            },
        ),
        migrations.CreateModel(
            name='Admin',
            fields=[
                ('adminID', models.BigAutoField(primary_key=True, serialize=False)),
                ('employee_name', models.CharField(max_length=150)),
                ('account', models.OneToOneField(db_column='accountID', on_delete=django.db.models.deletion.PROTECT, related_name='admin_profile', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Category',
            fields=[
                ('categoryID', models.BigAutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=80, unique=True)),
            ],
            options={
                'ordering': ['name'],
                'constraints': [models.UniqueConstraint(django.db.models.functions.text.Lower('name'), name='unique_category_lower')],
            },
        ),
        migrations.CreateModel(
            name='Customer',
            fields=[
                ('customerID', models.BigAutoField(primary_key=True, serialize=False)),
                ('height', models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True, validators=[django.core.validators.MinValueValidator(140), django.core.validators.MaxValueValidator(210)])),
                ('weight', models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True, validators=[django.core.validators.MinValueValidator(35), django.core.validators.MaxValueValidator(160)])),
                ('account', models.OneToOneField(db_column='accountID', on_delete=django.db.models.deletion.CASCADE, related_name='customer', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Cart',
            fields=[
                ('cartID', models.BigAutoField(primary_key=True, serialize=False)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('customer', models.OneToOneField(db_column='customerID', on_delete=django.db.models.deletion.CASCADE, related_name='cart', to='marketplace.customer')),
            ],
        ),
        migrations.CreateModel(
            name='Address',
            fields=[
                ('addressID', models.BigAutoField(primary_key=True, serialize=False)),
                ('recipient_name', models.CharField(max_length=120)),
                ('phone_number', models.CharField(max_length=20, validators=[django.core.validators.RegexValidator('^[+\\d ()-]{8,20}$', 'Enter a valid contact number.')])),
                ('address_line', models.CharField(max_length=250)),
                ('postal_code', models.CharField(max_length=6, validators=[django.core.validators.RegexValidator('^\\d{6}$', 'Enter a six-digit Singapore postal code.')])),
                ('country', models.CharField(default='Singapore', editable=False, max_length=30)),
                ('customer', models.ForeignKey(db_column='customerID', on_delete=django.db.models.deletion.CASCADE, related_name='addresses', to='marketplace.customer')),
            ],
            options={
                'ordering': ['pk'],
            },
        ),
        migrations.CreateModel(
            name='Order',
            fields=[
                ('orderID', models.BigAutoField(primary_key=True, serialize=False)),
                ('order_date', models.DateTimeField(auto_now_add=True)),
                ('order_status', models.CharField(choices=[('PROCESSING', 'Processing'), ('PARTIAL', 'Partially fulfilled'), ('COMPLETED', 'Completed'), ('CANCELLED', 'Cancelled')], default='PROCESSING', max_length=12)),
                ('payment_status', models.CharField(choices=[('PAID', 'Paid (demo)'), ('REFUNDED', 'Refunded (demo)')], default='PAID', max_length=12)),
                ('total_amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('shipping_name', models.CharField(max_length=120)),
                ('shipping_address', models.TextField()),
                ('shipping_postal', models.CharField(max_length=6)),
                ('shipping_phone', models.CharField(max_length=20)),
                ('address', models.ForeignKey(blank=True, db_column='addressID', null=True, on_delete=django.db.models.deletion.SET_NULL, to='marketplace.address')),
                ('customer', models.ForeignKey(db_column='customerID', on_delete=django.db.models.deletion.PROTECT, related_name='orders', to='marketplace.customer')),
            ],
            options={
                'ordering': ['-order_date', '-pk'],
            },
        ),
        migrations.CreateModel(
            name='Product',
            fields=[
                ('productID', models.BigAutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=160)),
                ('description', models.TextField()),
                ('price', models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
                ('image', models.ImageField(blank=True, upload_to='products/')),
                ('approval_status', models.CharField(choices=[('DRAFT', 'Draft'), ('PENDING', 'Pending review'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected'), ('SUSPENDED', 'Suspended')], default='DRAFT', max_length=12)),
                ('rejection_reason', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('category', models.ForeignKey(db_column='categoryID', on_delete=django.db.models.deletion.PROTECT, related_name='products', to='marketplace.category')),
                ('reviewed_by', models.ForeignKey(blank=True, db_column='reviewedByAdminID', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reviewed_products', to='marketplace.admin')),
            ],
            options={
                'ordering': ['name', 'pk'],
            },
        ),
        migrations.CreateModel(
            name='ProductVariant',
            fields=[
                ('productVariantID', models.BigAutoField(primary_key=True, serialize=False)),
                ('size', models.CharField(max_length=12)),
                ('colour', models.CharField(max_length=40)),
                ('sku', models.CharField(max_length=80, unique=True)),
                ('stock_quantity', models.PositiveIntegerField(default=0)),
                ('product', models.ForeignKey(db_column='productID', on_delete=django.db.models.deletion.PROTECT, related_name='variants', to='marketplace.product')),
            ],
            options={
                'ordering': ['pk'],
            },
        ),
        migrations.CreateModel(
            name='CartItem',
            fields=[
                ('cartItemID', models.BigAutoField(primary_key=True, serialize=False)),
                ('quantity', models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                ('cart', models.ForeignKey(db_column='cartID', on_delete=django.db.models.deletion.CASCADE, related_name='items', to='marketplace.cart')),
                ('variant', models.ForeignKey(db_column='productVariantID', on_delete=django.db.models.deletion.PROTECT, related_name='cart_items', to='marketplace.productvariant')),
            ],
            options={
                'ordering': ['pk'],
            },
        ),
        migrations.CreateModel(
            name='Seller',
            fields=[
                ('sellerID', models.BigAutoField(primary_key=True, serialize=False)),
                ('store_name', models.CharField(max_length=120, unique=True)),
                ('store_description', models.TextField()),
                ('email', models.EmailField(max_length=254)),
                ('approval_status', models.CharField(choices=[('PENDING', 'Pending'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected'), ('SUSPENDED', 'Suspended')], default='PENDING', max_length=12)),
                ('rejection_reason', models.TextField(blank=True)),
                ('commission_rate', models.DecimalField(decimal_places=4, default=Decimal('0.10'), max_digits=5, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(1)])),
                ('account', models.OneToOneField(db_column='accountID', on_delete=django.db.models.deletion.PROTECT, related_name='seller', to=settings.AUTH_USER_MODEL)),
                ('reviewed_by', models.ForeignKey(blank=True, db_column='reviewedByAdminID', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reviewed_sellers', to='marketplace.admin')),
            ],
            options={
                'ordering': ['store_name'],
            },
        ),
        migrations.AddField(
            model_name='product',
            name='seller',
            field=models.ForeignKey(db_column='sellerID', on_delete=django.db.models.deletion.PROTECT, related_name='products', to='marketplace.seller'),
        ),
        migrations.CreateModel(
            name='SellerOrder',
            fields=[
                ('sellerOrderID', models.BigAutoField(primary_key=True, serialize=False)),
                ('fulfilment_status', models.CharField(choices=[('PROCESSING', 'Processing'), ('SHIPPED', 'Shipped'), ('DELIVERED', 'Delivered'), ('CANCELLED', 'Cancelled')], default='PROCESSING', max_length=12)),
                ('tracking_number', models.CharField(blank=True, max_length=100)),
                ('shipped_at', models.DateTimeField(blank=True, null=True)),
                ('subtotal', models.DecimalField(decimal_places=2, max_digits=12)),
                ('commission_rate_applied', models.DecimalField(decimal_places=4, max_digits=5)),
                ('commission_amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('order', models.ForeignKey(db_column='orderID', on_delete=django.db.models.deletion.PROTECT, related_name='seller_orders', to='marketplace.order')),
                ('seller', models.ForeignKey(db_column='sellerID', on_delete=django.db.models.deletion.PROTECT, related_name='seller_orders', to='marketplace.seller')),
            ],
            options={
                'ordering': ['pk'],
            },
        ),
        migrations.CreateModel(
            name='OrderItem',
            fields=[
                ('orderItemID', models.BigAutoField(primary_key=True, serialize=False)),
                ('quantity', models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                ('unit_price_at_sale', models.DecimalField(decimal_places=2, max_digits=10)),
                ('line_subtotal', models.DecimalField(decimal_places=2, max_digits=12)),
                ('variant', models.ForeignKey(db_column='productVariantID', on_delete=django.db.models.deletion.PROTECT, related_name='order_items', to='marketplace.productvariant')),
                ('seller_order', models.ForeignKey(db_column='sellerOrderID', on_delete=django.db.models.deletion.PROTECT, related_name='items', to='marketplace.sellerorder')),
            ],
        ),
        migrations.CreateModel(
            name='Style',
            fields=[
                ('styleID', models.BigAutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=80, unique=True)),
                ('description', models.TextField(blank=True)),
            ],
            options={
                'ordering': ['name'],
                'constraints': [models.UniqueConstraint(django.db.models.functions.text.Lower('name'), name='unique_style_lower')],
            },
        ),
        migrations.CreateModel(
            name='ProductStyle',
            fields=[
                ('productStyleID', models.BigAutoField(primary_key=True, serialize=False)),
                ('product', models.ForeignKey(db_column='productID', on_delete=django.db.models.deletion.CASCADE, to='marketplace.product')),
                ('style', models.ForeignKey(db_column='styleID', on_delete=django.db.models.deletion.PROTECT, to='marketplace.style')),
            ],
        ),
        migrations.CreateModel(
            name='CustomerStylePreference',
            fields=[
                ('preferenceID', models.BigAutoField(primary_key=True, serialize=False)),
                ('customer', models.ForeignKey(db_column='customerID', on_delete=django.db.models.deletion.CASCADE, to='marketplace.customer')),
                ('style', models.ForeignKey(db_column='styleID', on_delete=django.db.models.deletion.PROTECT, to='marketplace.style')),
            ],
        ),
        migrations.AddConstraint(
            model_name='productvariant',
            constraint=models.UniqueConstraint(fields=('product', 'size', 'colour'), name='unique_product_variant'),
        ),
        migrations.AddConstraint(
            model_name='productvariant',
            constraint=models.CheckConstraint(condition=models.Q(('stock_quantity__gte', 0)), name='nonnegative_stock'),
        ),
        migrations.AddConstraint(
            model_name='cartitem',
            constraint=models.UniqueConstraint(fields=('cart', 'variant'), name='unique_cart_variant'),
        ),
        migrations.AddConstraint(
            model_name='cartitem',
            constraint=models.CheckConstraint(condition=models.Q(('quantity__gt', 0)), name='positive_cart_quantity'),
        ),
        migrations.AddConstraint(
            model_name='seller',
            constraint=models.UniqueConstraint(django.db.models.functions.text.Lower('store_name'), name='unique_store_lower'),
        ),
        migrations.AddConstraint(
            model_name='product',
            constraint=models.CheckConstraint(condition=models.Q(('price__gt', 0)), name='positive_product_price'),
        ),
        migrations.AddConstraint(
            model_name='sellerorder',
            constraint=models.UniqueConstraint(fields=('order', 'seller'), name='unique_order_seller'),
        ),
        migrations.AddConstraint(
            model_name='productstyle',
            constraint=models.UniqueConstraint(fields=('product', 'style'), name='unique_product_style'),
        ),
        migrations.AddConstraint(
            model_name='customerstylepreference',
            constraint=models.UniqueConstraint(fields=('customer', 'style'), name='unique_preference'),
        ),
    ]
