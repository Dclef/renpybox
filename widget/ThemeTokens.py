"""WinUI-inspired theme tokens shared by the application shell and pages."""

from dataclasses import dataclass

from qfluentwidgets import isDarkTheme


@dataclass(frozen=True)
class ThemePalette:
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_surface: str
    on_accent: str
    background: str
    surface: str
    surface_subtle: str
    surface_hover: str
    surface_pressed: str
    chrome: str
    text_primary: str
    text_secondary: str
    text_disabled: str
    border: str
    border_strong: str
    divider: str
    scrollbar: str
    scrollbar_hover: str
    success: str
    warning: str
    error: str
    info: str


# The neutral surfaces follow the Windows 11 light and dark palettes. Color is
# reserved for interaction and status, keeping the application workspace quiet.
LIGHT = ThemePalette(
    accent="#0078D4",
    accent_hover="#006CBE",
    accent_pressed="#005A9E",
    accent_surface="#E5F3FB",
    on_accent="#FFFFFF",
    background="#F3F3F3",
    surface="#FFFFFF",
    surface_subtle="#F9F9F9",
    surface_hover="#F6F6F6",
    surface_pressed="#EAEAEA",
    chrome="#F3F3F3",
    text_primary="#1A1A1A",
    text_secondary="#5D5D5D",
    text_disabled="#9A9A9A",
    border="rgba(0, 0, 0, 20)",
    border_strong="rgba(0, 0, 0, 36)",
    divider="rgba(0, 0, 0, 18)",
    scrollbar="#8A8A8A",
    scrollbar_hover="#666666",
    success="#0F7B0F",
    warning="#9D5D00",
    error="#C42B1C",
    info="#0067C0",
)

DARK = ThemePalette(
    accent="#4CC2FF",
    accent_hover="#60CDFF",
    accent_pressed="#0091EA",
    accent_surface="#0B3A4A",
    on_accent="#000000",
    background="#202020",
    surface="#2B2B2B",
    surface_subtle="#252525",
    surface_hover="#323232",
    surface_pressed="#3A3A3A",
    chrome="#202020",
    text_primary="#FFFFFF",
    text_secondary="#C7C7C7",
    text_disabled="#777777",
    border="rgba(255, 255, 255, 20)",
    border_strong="rgba(255, 255, 255, 36)",
    divider="rgba(255, 255, 255, 18)",
    scrollbar="#8A8A8A",
    scrollbar_hover="#B0B0B0",
    success="#6CCB5F",
    warning="#FCE100",
    error="#FF99A4",
    info="#60CDFF",
)


# PyQt-Fluent-Widgets 1.11.3 lightens qconfig.themeColor in dark mode. This
# seed maps its derived PRIMARY color to the WinUI dark accent above.
QFLUENT_DARK_ACCENT_SEED = "#2398D4"


def current_palette() -> ThemePalette:
    """Return the tokens for the active QFluentWidgets theme."""
    return DARK if isDarkTheme() else LIGHT


def current_qfluent_accent_seed() -> str:
    """Return the qconfig seed that produces the current visual accent."""
    return QFLUENT_DARK_ACCENT_SEED if isDarkTheme() else LIGHT.accent
