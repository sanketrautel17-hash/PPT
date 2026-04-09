from pydantic import BaseModel, Field


# ─── Placeholder ────────────────────────────────────────────────────────────

class TextStyle(BaseModel):
    font_family: str = ""
    font_size_pt: float = 0.0
    bold: bool = False
    italic: bool = False
    color: str = ""  # e.g. "scheme:dk1" or "#319D4F"


class PlaceholderPosition(BaseModel):
    left_emu: int = 0
    top_emu: int = 0
    width_emu: int = 0
    height_emu: int = 0


class Placeholder(BaseModel):
    idx: int
    name: str
    type: str  # TITLE, SUBTITLE, BODY, CENTER_TITLE, etc.
    position: PlaceholderPosition = Field(default_factory=PlaceholderPosition)
    text_style: TextStyle = Field(default_factory=TextStyle)
    max_chars_estimate: int = 0
    current_text: str = ""


# ─── Chart ──────────────────────────────────────────────────────────────────

class ChartMeta(BaseModel):
    shape_index: int
    chart_type: str  # BAR_CLUSTERED, PIE, LINE, etc.
    series_count: int = 0
    category_count: int = 0
    categories: list[str] = Field(default_factory=list)
    series_names: list[str] = Field(default_factory=list)
    current_values: list[list[float | None]] = Field(default_factory=list)
    color_scheme: list[str] = Field(default_factory=list)


# ─── Image ──────────────────────────────────────────────────────────────────

class ImageMeta(BaseModel):
    shape_index: int
    position: PlaceholderPosition = Field(default_factory=PlaceholderPosition)
    description: str = "image"  # inferred from position/size heuristic


# ─── Table ──────────────────────────────────────────────────────────────────

class TableMeta(BaseModel):
    shape_index: int
    rows: int
    cols: int
    header_row: list[str] = Field(default_factory=list)
    cell_style: dict = Field(default_factory=dict)


# ─── Theme ──────────────────────────────────────────────────────────────────

class ThemeColors(BaseModel):
    dk1: str = "#000000"
    dk2: str = "#44546A"
    lt1: str = "#FFFFFF"
    lt2: str = "#E7E6E6"
    accent1: str = "#319D4F"
    accent2: str = "#E42A2A"
    accent3: str = "#CBCBCB"
    accent4: str = "#1A6B30"
    accent5: str = "#F25555"
    accent6: str = "#70AD47"
    hyperlink: str = "#0563C1"


class ThemeFonts(BaseModel):
    major_font: str = "Calibri"  # headings
    minor_font: str = "Calibri"  # body


class Theme(BaseModel):
    colors: ThemeColors = Field(default_factory=ThemeColors)
    fonts: ThemeFonts = Field(default_factory=ThemeFonts)


# ─── Brand Rules ────────────────────────────────────────────────────────────

class FontRules(BaseModel):
    headings: str = ""
    body: str = ""
    bullets: str = ""


class BrandRules(BaseModel):
    tone: str = "Professional"
    font_rules: FontRules = Field(default_factory=FontRules)
    color_rules: str = ""
    formatting: list[str] = Field(default_factory=list)
    restrictions: list[str] = Field(default_factory=list)


# ─── Slide Layout ────────────────────────────────────────────────────────────

class SlideLayout(BaseModel):
    slide_index: int
    classification: str = "content_layout"  # "guidance" | "content_layout"
    placeholders: list[Placeholder] = Field(default_factory=list)
    charts: list[ChartMeta] = Field(default_factory=list)
    images: list[ImageMeta] = Field(default_factory=list)
    tables: list[TableMeta] = Field(default_factory=list)


# ─── Template Profile ────────────────────────────────────────────────────────

class TemplateProfile(BaseModel):
    name: str
    theme: Theme = Field(default_factory=Theme)
    brand_rules: BrandRules = Field(default_factory=BrandRules)
    slides: list[SlideLayout] = Field(default_factory=list)
    total_slides: int = 0
    usable_layouts: int = 0  # content_layout slides only

    def content_slides(self) -> list[SlideLayout]:
        """Return only slides classified as content_layout."""
        return [s for s in self.slides if s.classification == "content_layout"]
