"""Adaptadores mínimos para conservar contratos de la GUI heredada."""

from __future__ import annotations


class TextProxy:
    def __init__(self, text: str = ""):
        self.text = text

    def configure(self, **kwargs):
        if "text" in kwargs:
            self.text = str(kwargs["text"])

    config = configure

    def cget(self, key: str):
        if key == "text":
            return self.text
        return None


class ProgressProxy:
    def start(self, *_args, **_kwargs):
        return None

    def stop(self):
        return None

    def configure(self, **_kwargs):
        return None
