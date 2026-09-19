"""Router de páginas compatible con las llamadas notebook.select existentes."""

from __future__ import annotations


class PageRouter:
    def __init__(self):
        self.pages: dict[str, object] = {}
        self.by_widget: dict[object, str] = {}
        self.current: str | None = None
        self.on_change = None

    def register(self, name: str, widget) -> None:
        self.pages[name] = widget
        self.by_widget[widget] = name

    def select(self, target=None):
        if target is None:
            return self.current

        name = target if isinstance(target, str) else self.by_widget.get(target)
        if not name or name not in self.pages:
            return self.current

        for page_name, widget in self.pages.items():
            if page_name == name:
                widget.pack(fill="both", expand=True)
            else:
                widget.pack_forget()

        self.current = name
        if callable(self.on_change):
            self.on_change(name)
        return name
