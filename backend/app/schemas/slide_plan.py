from pydantic import BaseModel, Field, field_validator


class ChartSeries(BaseModel):
    name: str
    values: list[float | None] = Field(default_factory=list)


class ChartData(BaseModel):
    categories: list[str] = Field(default_factory=list)
    series: list[ChartSeries] = Field(default_factory=list)


class TableData(BaseModel):
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class SlideContent(BaseModel):
    # Keys are placeholder idx as strings (e.g. "0", "1", "2")
    # Values are either a plain string or a list of bullet strings
    placeholders: dict[str, str | list[str]] = Field(default_factory=dict)
    chart_data: ChartData | None = None
    table_data: TableData | None = None

    @field_validator("placeholders", mode="before")
    @classmethod
    def _normalize_placeholders(cls, value):
        """
        Coerce LLM drift into the declared schema:
        - null placeholder values become empty strings
        - non-string scalars become strings
        - list items are normalized to strings with null -> ""
        """
        if value is None:
            return {}
        if not isinstance(value, dict):
            return value

        normalized: dict[str, str | list[str]] = {}
        for key, item in value.items():
            key_str = str(key)
            if item is None:
                normalized[key_str] = ""
            elif isinstance(item, list):
                normalized[key_str] = ["" if v is None else str(v) for v in item]
            else:
                normalized[key_str] = str(item)
        return normalized


class SlidePlanItem(BaseModel):
    slide_type: str                     # e.g. "title", "bullet", "chart_bar", "divider"
    template_slide_index: int           # Which slide to use from the template
    purpose: str                        # Human-readable description of the slide
    content: SlideContent = Field(default_factory=SlideContent)


class SlidePlan(BaseModel):
    metadata: dict = Field(default_factory=dict)
    slides: list[SlidePlanItem] = Field(default_factory=list)


class SlideOutlineItem(BaseModel):
    slide_type: str
    template_slide_index: int
    purpose: str
