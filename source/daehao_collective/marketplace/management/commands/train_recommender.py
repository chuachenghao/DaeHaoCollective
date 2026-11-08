import json

import numpy as np
import pandas as pd
from joblib import dump
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
    confusion_values = []
    for row in confusion:
        confusion_values.append([int(row[0]), int(row[1])])
    results = {
        "accuracy": round(metrics.accuracy_score(test_labels, predicted), 6),
        "confusion_matrix": confusion_values,
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


class Command(BaseCommand):
    help = "Train the course-style decision tree and save the model and measured validation results."

    def handle(self, *args, **options):
        metadata = train_model()
        self.stdout.write("Saved ml/recommender.joblib and ml/metadata.json.")
        self.stdout.write(
            "Held-out synthetic accuracy: " + str(metadata["metrics"]["accuracy"])
        )
        self.stdout.write(
            "These results do not measure garment fit or real customer preferences."
        )
