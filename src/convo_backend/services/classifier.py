import onnxruntime as ort
import numpy as np
from dataclasses import dataclass
from typing import Optional
import os
import logging
from convo_backend.config import Config
from transformers import AutoTokenizer
import torch
import time
from numpy import ndarray

@dataclass
class ClassificationResult:
    needs_api: bool
    priority: Optional[str]
    api_logits : ndarray

class TextClassifier:
    """
    A classifier that uses a quantized ONNX model to classify incoming text.

    Attributes:
        session (onnxruntime.InferenceSession): The ONNX runtime session.
        input_name (str): The name of the input node.
        output_names (list): The names of the output nodes.
    """
    def __init__(self, tokenizer_name: str = "distilbert-base-uncased"):
        """
        Initialize the TextClassifier with the specified ONNX model.

        Args:
            model_path (str, optional): Path to the ONNX model file.
                Defaults to 'models/classifier.onnx'.
        """
        self.session = ort.InferenceSession(Config.CLASSIFIER_MODEL_PATH, providers=["CPUExecutionProvider"])
        self.tokenizer = AutoTokenizer.from_pretrained(tokenizer_name)

        self.priority_map = {
            0: "not directed",
            1: "low",
            2: "medium",
            3: "high"
        }

    def classify(self, text: str, max_len=Config.CLASSIFIER_MAX_LENGTH):
        start_time = time.time()

        # Tokenize
        encoding = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=max_len,
            padding="max_length"
        )
        input_ids = encoding["input_ids"].numpy()
        attention_mask = encoding["attention_mask"].numpy()

        # ONNX Inference
        logits_api, logits_priority = self.session.run(
            None,
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask
            }
        )

        # Convert numpy outputs to torch and get predictions
        pred_api = torch.argmax(torch.from_numpy(logits_api), dim=1).item()
        pred_priority = torch.argmax(torch.from_numpy(logits_priority), dim=1).item()

        # Interpret results
        needs_api = (pred_api == 1)
        priority_label = self.priority_map.get(pred_priority, "unknown")

        end_time = time.time()
        latency = end_time - start_time

        print(latency)
        print(f"Probablity of needing api: {pred_api}")
        print(f"Logit of needing an API: {logits_api}")

        return ClassificationResult(
            needs_api=needs_api,
            priority=priority_label,
            api_logits=logits_api
        ) 
