import json

import numpy as np
import pandas as pd
from joblib import dump, load
from sklearn import metrics, tree
from sklearn.model_selection import train_test_split
from django.core.management.base import BaseCommand

from marketplace.recommendations import (
    CATEGORY_SLUGS,
    FEATURE_NAMES,
    METADATA_PATH,
    MODEL_PATH,
    SCHEMA_VERSION,
    STYLE_SLUGS,
    _load_artifact,
)
from marketplace.sizing import (
    SIZE_FEATURE_NAMES,
    SIZE_LABELS,
    SIZE_SCHEMA_VERSION,
    SUPPORTED_RANGES,
    _load_size_model,
)

RANDOM_SEED = 2108


def train_model():
    np.random.seed(RANDOM_SEED)
    dataset_path = MODEL_PATH.parent / "synthetic_pairs.csv"
    dataset = pd.read_csv(dataset_path)
    features = dataset.drop("relevant", axis=1)
    labels = dataset["relevant"]
    if list(features.columns) != FEATURE_NAMES:
        raise ValueError("The dataset columns do not match the model inputs.")
    train_rows, test_rows, train_labels, test_labels = train_test_split(
        features, labels, train_size=0.8, test_size=0.2, shuffle=True, stratify=labels
    )
    model = tree.DecisionTreeClassifier(criterion="gini", splitter="best", max_depth=10)
    model = model.fit(train_rows, train_labels)
    predicted = model.predict(test_rows)
    confusion = metrics.confusion_matrix(test_labels, predicted, labels=[0, 1])
    results = {
        "accuracy": round(metrics.accuracy_score(test_labels, predicted), 6),
        "confusion_matrix": confusion.tolist(),
        "precision": None,
        "recall": None,
        "f1": None,
        "roc_auc": None,
    }
    artifact = {
        "model": model,
        "schema_version": SCHEMA_VERSION,
        "feature_names": FEATURE_NAMES,
        "style_slugs": STYLE_SLUGS,
        "category_slugs": CATEGORY_SLUGS,
    }
    dump(artifact, MODEL_PATH)
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": "DecisionTreeClassifier",
        "source": "Fictional customer-product pairs in the supplied synthetic_pairs.csv dataset",
        "random_seed": RANDOM_SEED,
        "dataset_rows": len(dataset),
        "training_rows": len(train_rows),
        "validation_rows": len(test_rows),
        "split": "Stratified 80% training / 20% held-out validation",
        "target": "Fictional binary customer-product relevance (0 / 1)",
        "feature_names": FEATURE_NAMES,
        "style_slugs": STYLE_SLUGS,
        "category_slugs": CATEGORY_SLUGS,
        "supported_ranges": {"height_cm": [140, 210], "weight_kg": [35, 160]},
        "metrics": results,
        "metric_note": "Held-out synthetic accuracy measures invented labels, not real customers, fit or commercial performance.",
        "parameters": {"criterion": "gini", "splitter": "best", "max_depth": 10},
        "ranking": "Predicted class 1 before class 0, then stable product id for ties",
    }
    with open(METADATA_PATH, "w") as metadata_file:
        json.dump(metadata, metadata_file, indent=2)
    _load_artifact(MODEL_PATH)
    return metadata


def train_size_model():
    """Append an independent synthetic size tree without refitting style relevance."""
    _load_artifact(MODEL_PATH)
    artifact = load(MODEL_PATH)
    with open(METADATA_PATH) as metadata_file:
        metadata = json.load(metadata_file)
    if metadata.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("The style metadata has an incompatible schema.")

    source = pd.read_csv(MODEL_PATH.parent / "synthetic_pairs.csv")
    dataset = source[SIZE_FEATURE_NAMES].copy()
    # This reference rule is invented for the demonstration, not a retailer chart.
    size_labels = []
    for height, weight in zip(dataset["height_cm"], dataset["weight_kg"]):
        reference_weight = weight - 0.45 * (height - 170)
        if reference_weight < 45:
            size = "XS"
        elif reference_weight < 58:
            size = "S"
        elif reference_weight < 72:
            size = "M"
        elif reference_weight < 86:
            size = "L"
        elif reference_weight < 105:
            size = "XL"
        else:
            size = "XXL"
        size_labels.append(size)
    dataset["size"] = size_labels
    dataset.to_csv(MODEL_PATH.parent / "synthetic_sizes.csv", index=False)
    features, labels = dataset[SIZE_FEATURE_NAMES], dataset["size"]
    train_rows, test_rows, train_labels, test_labels = train_test_split(
        features, labels, train_size=0.8, test_size=0.2, shuffle=True,
        stratify=labels, random_state=RANDOM_SEED,
    )
    model = tree.DecisionTreeClassifier(
        criterion="gini", splitter="best", max_depth=10,
        min_samples_leaf=3, random_state=RANDOM_SEED,
    )
    model = model.fit(train_rows, train_labels)
    predicted = model.predict(test_rows)
    artifact.update(
        size_model=model,
        size_schema_version=SIZE_SCHEMA_VERSION,
        size_feature_names=SIZE_FEATURE_NAMES,
        size_labels=SIZE_LABELS,
    )
    metadata["sizing"] = {
        "schema_version": SIZE_SCHEMA_VERSION,
        "algorithm": "DecisionTreeClassifier",
        "source": "Height and weight copied from synthetic_pairs.csv; all size labels are invented for this demonstration.",
        "dataset": "synthetic_sizes.csv",
        "dataset_rows": len(dataset),
        "training_rows": len(train_rows),
        "validation_rows": len(test_rows),
        "split": "Stratified 80% training / 20% held-out validation",
        "random_seed": RANDOM_SEED,
        "target": "Invented starting size estimate; not a retailer size chart or physical fit prediction",
        "feature_names": SIZE_FEATURE_NAMES,
        "labels": SIZE_LABELS,
        "supported_ranges": SUPPORTED_RANGES,
        "reference_rule": {
            "formula": "reference_weight = weight_kg - 0.45 * (height_cm - 170)",
            "upper_boundaries_exclusive": [45, 58, 72, 86, 105],
            "ordered_labels": SIZE_LABELS,
            "note": "Fictional boundaries invented for the demo; no real garment measurements or customer fit outcomes were used.",
        },
        "parameters": {
            "criterion": "gini", "splitter": "best", "max_depth": 10,
            "min_samples_leaf": 3, "random_state": RANDOM_SEED,
        },
        "feature_importance": {
            name: round(float(value), 6)
            for name, value in zip(SIZE_FEATURE_NAMES, model.feature_importances_)
        },
        "metrics": {
            "accuracy": round(float(metrics.accuracy_score(test_labels, predicted)), 6),
            "confusion_matrix": metrics.confusion_matrix(
                test_labels, predicted, labels=SIZE_LABELS
            ).tolist(),
            "confusion_matrix_labels": SIZE_LABELS,
        },
        "metric_note": "Held-out synthetic accuracy measures recovery of invented labels only. It does not measure real size accuracy or guarantee fit.",
    }
    dump(artifact, MODEL_PATH)
    with open(METADATA_PATH, "w") as metadata_file:
        json.dump(metadata, metadata_file, indent=2)
    _load_artifact(MODEL_PATH)
    _load_size_model(MODEL_PATH)
    return metadata


class Command(BaseCommand):
    help = "Train the style and synthetic size decision trees and save measured validation results."

    def add_arguments(self, parser):
        parser.add_argument(
            "--size-only", action="store_true",
            help="Add or retrain the synthetic size estimate while preserving the saved style tree.",
        )

    def handle(self, *args, **options):
        if not options["size_only"]:
            train_model()
        metadata = train_size_model()
        self.stdout.write("Saved ml/recommender.joblib, ml/metadata.json and ml/synthetic_sizes.csv.")
        self.stdout.write(
            "Held-out synthetic style accuracy: " + str(metadata["metrics"]["accuracy"])
        )
        self.stdout.write(
            "Held-out invented size-label accuracy: " + str(metadata["sizing"]["metrics"]["accuracy"])
        )
        self.stdout.write("These results do not measure real customer preferences, size accuracy or garment fit.")
