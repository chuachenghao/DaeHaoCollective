import json
from types import SimpleNamespace

import pandas as pd
from joblib import load
from django.conf import settings
from django.utils.text import slugify

from .models import Category, Product, ProductVariant, Style

SCHEMA_VERSION = 2
STYLE_SLUGS = ["minimal", "casual", "workwear", "streetwear", "formal", "vintage"]
CATEGORY_SLUGS = ["tops", "bottoms", "outerwear", "dresses"]
FEATURE_NAMES = (
    ["height_cm", "weight_kg", "shared_style_count"]
    + ["customer_" + slug for slug in STYLE_SLUGS]
    + ["product_" + slug for slug in STYLE_SLUGS]
    + ["category_" + slug for slug in CATEGORY_SLUGS]
)
MODEL_PATH = settings.BASE_DIR / "ml" / "recommender.joblib"
METADATA_PATH = settings.BASE_DIR / "ml" / "metadata.json"


def feature_row(height, weight, customer_styles, product_styles, category):
    customer_styles, product_styles = set(customer_styles), set(product_styles)
    return (
        [float(height), float(weight), len(customer_styles & product_styles)]
        + [int(slug in customer_styles) for slug in STYLE_SLUGS]
        + [int(slug in product_styles) for slug in STYLE_SLUGS]
        + [int(category == slug) for slug in CATEGORY_SLUGS]
    )


def _load_artifact(model_path):
    artifact = load(model_path)
    if (
        not isinstance(artifact, dict)
        or artifact.get("schema_version") != SCHEMA_VERSION
    ):
        raise ValueError("The saved model has an incompatible schema.")
    if artifact.get("feature_names") != FEATURE_NAMES:
        raise ValueError("The saved model uses different input columns.")
    if (
        artifact.get("style_slugs") != STYLE_SLUGS
        or artifact.get("category_slugs") != CATEGORY_SLUGS
    ):
        raise ValueError("The saved model uses a different vocabulary.")
    model = artifact["model"]
    if model.n_features_in_ != len(FEATURE_NAMES):
        raise ValueError("The saved model uses a different number of inputs.")
    probe_rows = pd.DataFrame(
        [feature_row(172, 65, ["minimal"], ["minimal"], "tops")], columns=FEATURE_NAMES
    )
    probe = model.predict(probe_rows)
    if len(probe) != 1 or probe[0] not in [0, 1]:
        raise ValueError("The model's inference probe failed.")
    return model


def model_readiness():
    result = {
        "ready": False,
        "message": "",
        "metadata": {},
        "metrics": {},
        "unsupported_categories": [],
        "unsupported_styles": [],
    }
    for category in Category.objects.all():
        if slugify(category.name) not in CATEGORY_SLUGS:
            result["unsupported_categories"].append(category.name)
    for style in Style.objects.all():
        if slugify(style.name) not in STYLE_SLUGS:
            result["unsupported_styles"].append(style.name)
    try:
        with open(METADATA_PATH) as metadata_file:
            metadata = json.load(metadata_file)
        result["metadata"] = metadata
        result["metrics"] = metadata.get("metrics", {})
        if (
            metadata.get("schema_version") != SCHEMA_VERSION
            or metadata.get("feature_names") != FEATURE_NAMES
        ):
            raise ValueError(
                "The metadata input schema does not match the application."
            )
        if (
            metadata.get("style_slugs") != STYLE_SLUGS
            or metadata.get("category_slugs") != CATEGORY_SLUGS
        ):
            raise ValueError("The metadata vocabulary does not match the application.")
        _load_artifact(MODEL_PATH)
    except FileNotFoundError:
        result["message"] = (
            "Model artifact or metadata is missing. Run python manage.py train_recommender."
        )
        return result
    except Exception:
        result["message"] = (
            "The trusted model could not pass its artifact, schema or inference checks. Retrain the model."
        )
        return result
    if result["unsupported_categories"] or result["unsupported_styles"]:
        result["message"] = (
            "The catalogue contains categories or styles outside the trained vocabulary. Update the training vocabulary and retrain."
        )
        return result
    result.update(
        ready=True,
        message="Ready — trained on synthetic customer-product pairs; schema and inference probe passed.",
    )
    return result


def available_products(queryset=None):
    if queryset is None:
        queryset = Product.objects.all()
    queryset = queryset.filter(
        is_active=True,
        approval_status="APPROVED",
        seller__approval_status="APPROVED",
    )
    products = []
    for product in queryset:
        variants = ProductVariant.objects.filter(product=product, stock_quantity__gt=0)
        for variant in variants:
            products.append(product)
            break
    return products


def recommend_products(customer, queryset=None, preview_style=None):
    products = list(available_products(queryset))
    result = {
        "products": products,
        "personalised": False,
        "reason": "",
        "message": "",
        "preview": False,
        "preview_style": "",
        "sample_measurements": False,
        "preferred_styles": [],
        "model_pick_count": 0,
        "shared_style_count": 0,
        "evaluated_count": len(products),
    }
    for product in products:
        product.shared_styles = []
        product.style_labels = [style.name for style in product.get_styles()]
        product.model_ranked = False
    if preview_style is not None:
        preview_preferences = [
            style
            for style in Style.objects.all()
            if slugify(style.name) == preview_style and preview_style in STYLE_SLUGS
        ]
        if not preview_preferences:
            result.update(
                reason="invalid_preview",
                message="Choose one of the six available styles to preview recommendations.",
            )
            return result
        use_saved_measurements = (
            customer is not None
            and customer.height is not None
            and customer.weight is not None
            and 140 <= float(customer.height) <= 210
            and 35 <= float(customer.weight) <= 160
        )
        customer = SimpleNamespace(
            height=customer.height if use_saved_measurements else 172,
            weight=customer.weight if use_saved_measurements else 65,
            get_styles=lambda: preview_preferences,
        )
        result.update(
            preview=True,
            preview_style=preview_style,
            sample_measurements=not use_saved_measurements,
            preferred_styles=[style.name for style in preview_preferences],
        )
    if not products:
        result.update(
            reason="no_stock",
            message="No available clothing matches these filters. Try broadening your selection.",
        )
        return result
    if customer is None:
        result.update(
            reason="missing_profile",
            message="Curated selection — sign in and add an optional profile for personalised discovery.",
        )
        return result
    preferences = list(customer.get_styles())
    result["preferred_styles"] = [style.name for style in preferences]
    if customer.height is None or customer.weight is None or not preferences:
        result.update(
            reason="incomplete_profile",
            message="Curated selection — add your height, weight and preferred styles to enable For You.",
        )
        return result
    if not (
        140 <= float(customer.height) <= 210 and 35 <= float(customer.weight) <= 160
    ):
        result.update(
            reason="unsupported_profile",
            message="Curated selection — your measurements are outside the demo model's supported range. Edit your profile to try again.",
        )
        return result
    readiness = model_readiness()
    if not readiness["ready"]:
        unsupported = (
            readiness["unsupported_categories"] or readiness["unsupported_styles"]
        )
        if unsupported:
            result.update(
                reason="unsupported_taxonomy",
                message=(
                    "Curated selection — a catalogue style or category is not supported by the current model. "
                    "You can keep shopping while the model vocabulary is updated."
                ),
            )
        else:
            result.update(
                reason="model_unavailable",
                message=(
                    "Curated selection — personalisation is temporarily unavailable. "
                    "You can keep shopping, or edit your profile and try again."
                ),
            )
        return result
    try:
        customer_styles = {slugify(style.name) for style in preferences}
        rows = [
            feature_row(
                customer.height,
                customer.weight,
                customer_styles,
                [slugify(style.name) for style in product.get_styles()],
                slugify(product.category.name),
            )
            for product in products
        ]
        model = _load_artifact(MODEL_PATH)
        inputs = pd.DataFrame(rows, columns=FEATURE_NAMES)
        scores = model.predict(inputs)
        if len(scores) != len(products) or any(score not in [0, 1] for score in scores):
            raise ValueError("Unexpected prediction output.")
        for product, score in zip(products, scores):
            product.recommendation_score = int(score)
            product.model_ranked = True
            product.shared_styles = [
                style.name
                for style in product.get_styles()
                if slugify(style.name) in customer_styles
            ]
        products.sort(key=lambda p: (-p.recommendation_score, p.pk))
        for rank, product in enumerate(products, start=1):
            product.recommendation_rank = rank
    except Exception:
        for product in products:
            product.model_ranked = False
            product.shared_styles = []
        result.update(
            reason="model_error",
            message="Curated selection — personalisation is temporarily unavailable. You can keep shopping and try again later.",
        )
        return result
    result.update(
        products=products,
        personalised=True,
        model_pick_count=sum(p.recommendation_score for p in products),
        shared_style_count=sum(bool(p.shared_styles) for p in products),
        reason="model_ranked",
        message=("Previewing " if result["preview"] else "Using your saved ")
        + " / ".join(style.name for style in preferences)
        + " preferences. The trained model brings predicted relevant pieces to the front of your selection.",
    )
    return result
