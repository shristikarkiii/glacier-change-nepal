"""Figure styling: one palette, two modes, applied to every output.

Colour is assigned by the job it does rather than by taste:

* elevation and ice extent are *magnitude* -> single-hue sequential ramps,
  light to dark, lightness strictly monotonic;
* epochs and the this-study/thesis contrast are *identity* -> categorical
  hues that stay separable under all three common colour-vision
  deficiencies;
* every figure is rendered for a light and a dark surface, each stepped for
  its own background rather than flipped.
"""

from __future__ import annotations

from dataclasses import dataclass

from matplotlib.colors import LinearSegmentedColormap


@dataclass(frozen=True)
class Theme:
    name: str
    surface: str
    page: str
    ink: str
    ink_secondary: str
    ink_muted: str
    grid: str
    axis: str
    # Sequential ramps (light -> dark), one hue each.
    canopy: tuple[str, ...]
    lossyear: tuple[str, ...]
    elevation: tuple[str, ...]
    # Categorical identity slots, in fixed order.
    series: tuple[str, ...]
    loss: str
    gain: str
    # Neutral backdrop for context layers.
    backdrop: str
    water: str

    def cmap(self, ramp: tuple[str, ...], name: str) -> LinearSegmentedColormap:
        return LinearSegmentedColormap.from_list(f"{name}_{self.name}", list(ramp))


LIGHT = Theme(
    name="light",
    surface="#fcfcfb",
    page="#f9f9f7",
    ink="#0b0b0b",
    ink_secondary="#52514e",
    ink_muted="#898781",
    grid="#e1e0d9",
    axis="#c3c2b7",
    canopy=("#e8f3e4", "#c9e4c2", "#a3d199", "#79bb6f", "#51a248", "#33862f", "#1d6a1d", "#0f4e13"),
    lossyear=("#fde3e2", "#f8c3c1", "#f09e9c", "#e47876", "#d55351", "#b73b39", "#932a29", "#6d1f1e"),
    elevation=("#f2efe6", "#ddd6c2", "#c6bb9d", "#ab9d7b", "#8d7d5c", "#6d5f41", "#4d422a", "#2e2616"),
    series=("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"),
    loss="#e34948",
    gain="#2a78d6",
    backdrop="#dedcd4",
    water="#cdd9e4",
)

DARK = Theme(
    name="dark",
    surface="#1a1a19",
    page="#0d0d0d",
    ink="#ffffff",
    ink_secondary="#c3c2b7",
    ink_muted="#898781",
    grid="#2c2c2a",
    axis="#383835",
    canopy=("#0f2a11", "#16401a", "#1d5722", "#256f2b", "#2f8835", "#44a147", "#66b965", "#93d08f"),
    lossyear=("#4a1616", "#661f1e", "#832927", "#a13432", "#bd433f", "#d15f5c", "#e08381", "#eda9a7"),
    elevation=("#241e12", "#3a3120", "#52462e", "#6b5c3e", "#877550", "#a49066", "#c2ad82", "#ded0ab"),
    series=("#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"),
    loss="#e66767",
    gain="#3987e5",
    backdrop="#3a3a37",
    water="#2b3a47",
)

THEMES = (LIGHT, DARK)


def rc(theme: Theme) -> dict:
    """Matplotlib rcParams for one theme - recessive chrome, text in ink."""
    return {
        "figure.facecolor": theme.surface,
        "axes.facecolor": theme.surface,
        "savefig.facecolor": theme.surface,
        "text.color": theme.ink,
        "axes.labelcolor": theme.ink_secondary,
        "axes.edgecolor": theme.axis,
        "xtick.color": theme.ink_muted,
        "ytick.color": theme.ink_muted,
        "xtick.labelcolor": theme.ink_secondary,
        "ytick.labelcolor": theme.ink_secondary,
        "grid.color": theme.grid,
        "grid.linewidth": 0.8,
        "axes.grid": False,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.linewidth": 0.8,
        "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"],
        "font.size": 9,
        "figure.dpi": 160,
        "savefig.dpi": 160,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.25,
    }


def suffix(theme: Theme) -> str:
    return "" if theme.name == "light" else "-dark"
