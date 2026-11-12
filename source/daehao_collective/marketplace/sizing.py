"""A separate synthetic size estimate; retailer measurements still determine fit."""

import json
import math

import pandas as pd
from django.conf import settings
from joblib import load

MODEL_PATH = settings.BASE_DIR / "ml" / "recommender.joblib"
METADATA_PATH = settings.BASE_DIR / "ml" / "metadata.json"
STYLE_SCHEMA_VERSION = 2
SIZE_SCHEMA_VERSION = 1
SIZE_FEATURE_NAMES = ["height_cm", "weight_kg"]
SIZE_LABELS = ["XS", "S", "M", "L", "XL", "XXL"]
SUPPORTED_RANGES = {"height_cm": [140, 210], "weight_kg": [35, 160]}
ESTIMATE_NOTE = (
    "A starting estimate from a model trained on invented size labels. "
    "Check the retailer's garment measurements; this is not a fit guarantee."
)


def _load_size_model(model_path):
    artifact = load(model_path)
    if not isinstance(artifact, dict) or artifact.get("schema_version") != STYLE_SCHEMA_VERSION:
        raise ValueError("The model artifact has an incompatible schema.")
    if artifact.get("size_schema_version") != SIZE_SCHEMA_VERSION:
        raise ValueError("The saved size model has an incompatible schema.")
    if artifact.get("size_feature_names") != SIZE_FEATURE_NAMES:
        raise ValueError("The saved size model uses different input columns.")
    if artifact.get("size_labels") != SIZE_LABELS:
        raise ValueError("The saved size model uses different size labels.")
    model = artifact["size_model"]
    if model.n_features_in_ != len(SIZE_FEATURE_NAMES):
        raise ValueError("The saved size model uses a different number of inputs.")
    if list(model.feature_names_in_) != SIZE_FEATURE_NAMES:
        raise ValueError("The fitted size model uses different input columns.")
    if set(model.classes_) != set(SIZE_LABELS):
        raise ValueError("The fitted size model uses different output labels.")
    probe = model.predict(pd.DataFrame([[172.0, 65.0]], columns=SIZE_FEATURE_NAMES))
    if len(probe) != 1 or probe[0] not in SIZE_LABELS:
        raise ValueError("The size model's inference probe failed.")
    return model


def _size_readiness():
    result = {"ready": False, "message": "", "metadata": {}}
    try:
        with open(METADATA_PATH) as metadata_file:
            metadata = json.load(metadata_file)
        sizing = metadata.get("sizing", {})
        result["metadata"] = sizing
        if (
            metadata.get("schema_version") != STYLE_SCHEMA_VERSION
            or sizing.get("schema_version") != SIZE_SCHEMA_VERSION
            or sizing.get("feature_names") != SIZE_FEATURE_NAMES
            or sizing.get("labels") != SIZE_LABELS
            or sizing.get("supported_ranges") != SUPPORTED_RANGES
        ):
            raise ValueError("The sizing metadata does not match the application.")
        model = _load_size_model(MODEL_PATH)
    except FileNotFoundError:
        result["message"] = "The size model is unavailable. Check retailer measurements."
        return result, None
    except Exception:
        result["message"] = "The size model could not pass its checks. Check retailer measurements."
        return result, None
    result.update(ready=True, message=ESTIMATE_NOTE)
    return result, model


def size_model_readiness():
    result, _ = _size_readiness()
    return result


def predict_size(height, weight):
    result = {"ready": False, "size": "", "reason": "", "message": ""}
    if height is None or weight is None or height == "" or weight == "":
        result.update(
            reason="missing_measurements",
            message="Add your height and weight to see a starting size estimate.",
        )
        return result
    try:
        if isinstance(height, bool) or isinstance(weight, bool):
            raise ValueError("Measurements must be numbers.")
        height, weight = float(height), float(weight)
        if not math.isfinite(height) or not math.isfinite(weight):
            raise ValueError("Measurements must be finite numbers.")
    except (TypeError, ValueError, OverflowError):
        result.update(
            reason="invalid_measurements",
            message="Enter valid height and weight measurements to see a size estimate.",
        )
        return result
    if not 140 <= height <= 210 or not 35 <= weight <= 160:
        result.update(
            reason="unsupported_measurements",
            message="Size estimates support heights from 140–210 cm and weights from 35–160 kg.",
        )
        return result
    readiness, model = _size_readiness()
    if not readiness["ready"]:
        result.update(reason="model_unavailable", message=readiness["message"])
        return result
    try:
        predicted = model.predict(pd.DataFrame([[height, weight]], columns=SIZE_FEATURE_NAMES))
        if len(predicted) != 1 or predicted[0] not in SIZE_LABELS:
            raise ValueError("The size model returned an unsupported label.")
    except Exception:
        result.update(
            reason="model_error",
            message="A size estimate is unavailable right now. Check retailer measurements.",
        )
        return result
    result.update(ready=True, size=str(predicted[0]), reason="size_predicted", message=ESTIMATE_NOTE)
    return result


def product_size_guidance(product, height, weight, colour="", prediction=None):
    result = dict(prediction) if prediction is not None else predict_size(height, weight)
    colour = str(colour or "").strip()
    result.update(available=False, availability="unknown", colour=colour)
    if not result.get("ready"):
        return result
    if result.get("size") not in SIZE_LABELS:
        result.update(
            ready=False, size="", reason="model_error",
            message="A size estimate is unavailable right now. Check retailer measurements.",
        )
        return result
    variants = list(product.variants.all())
    supported = [variant for variant in variants if variant.size.strip().upper() in SIZE_LABELS]
    if not supported:
        result.update(
            ready=False, size="", reason="unsupported_size_labels",
            message="This item uses different retailer size labels. Check the retailer's measurements.",
        )
        return result
    matching = [
        variant for variant in supported
        if variant.size.strip().upper() == result["size"]
        and (not colour or variant.colour.strip().casefold() == colour.casefold())
    ]
    colour_note = " in " + colour if colour else ""
    if not matching:
        availability = "not_sold"
        stock_message = "is not sold for this item"
    elif any(variant.stock_quantity > 0 for variant in matching):
        availability = "in_stock"
        stock_message = "is in stock"
    else:
        availability = "sold_out"
        stock_message = "is sold out"
    result.update(
        available=availability == "in_stock",
        availability=availability,
        reason="predicted_size_" + availability,
        message=f"Estimated size {result['size']}{colour_note} {stock_message}. " + ESTIMATE_NOTE,
    )
    return result
