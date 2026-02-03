"""
Calamum 'Ghost Console' (TUI)
-----------------------------
A Digital Brutalism operational dashboard for the Calamum Moltbook Observer.

Status: PROTOTYPE
Owner: ORACL-Prime
"""

import datetime
from textual.app import App, ComposeResult
from textual.containers import Grid, Container
from textual.widgets import Header, Footer, Static, Log, Button
from textual.binding import Binding
import plotext as plt

class IntegrityDiamond(Static):
    """A 4-axis radar chart showing system health balance."""
    
    def on_mount(self) -> None:
        self.update_chart()

    def update_chart(self) -> None:
        plt.clf()
        plt.theme("dark")
        plt.frame(False)
        plt.grid(False)
        
        # Axes: Availability (Top), Integrity (Right), Capacity (Bottom), Freshness (Left)
        # Perfect Score: [1, 1, 1, 1]
        labels = ["Avail", "Integrity", "Capacity", "Fresh"]
        data = [1, 1, 1, 1]  # Mock data: Perfect health
        
        plt.radar(data, labels)
        plt.title("Integrity Shield")
        
        # Render plotext to string
        self.update(plt.build())

class BioRhythm(Static):
    """A scrolling ECG-style line chart representing heartbeat/latency."""
    
    def compose(self) -> ComposeResult:
        yield Static("BIO-RHYTHM: [Active] 72bpm (40ms lag)")
        # Placeholder for scrolling wave implementation

class DensityHistogram(Static):
    """Vertical bars showing collection volume and type."""

    def compose(self) -> ComposeResult:
        yield Static("DENSITY: [Low] 15 msg/s")
        # Placeholder for sparkline implementation

class ControlDeck(Container):
    """Slide-out control panel."""
    
    DEFAULT_CSS = """
    ControlDeck {
        layer: overlay;
        width: 30;
        dock: right;
        background: $surface;
        border-left: heavy $accent;
        offset-x: 100%;
        transition: offset-x 500ms;
    }
    ControlDeck.visible {
        offset-x: 0%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(" CONTROL DECK ", classes="header")
        yield Button("🛑 KILL SWITCH", id="btn_kill", variant="error")
        yield Button("⏸️ PAUSE", id="btn_pause", variant="warning")
        yield Button("🔄 ROTATE", id="btn_rotate", variant="primary")

class CalamumConsole(App):
    """The main TUI Application."""

    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 3;
        grid-rows: 3 1fr 10;
        grid-columns: 2fr 1fr;
    }

    .box {
        border: solid green;
        padding: 1;
    }

    IntegrityDiamond {
        row-span: 2;
        border: heavy cyan;
    }

    Log {
        column-span: 2;
        border-top: solid white;
        height: 10;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        Binding("shift+k", "kill_switch", "Kill Switch", show=False),
        Binding("p", "pause", "Pause/Resume"),
        Binding("r", "rotate", "Rotate Logs"),
        Binding("space", "toggle_deck", "Control Deck"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield IntegrityDiamond(classes="box")
        yield BioRhythm(classes="box")
        yield DensityHistogram(classes="box")
        yield Log(id="syslog")
        yield Footer()
        yield ControlDeck(id="deck")

    def action_toggle_deck(self) -> None:
        deck = self.query_one("#deck", ControlDeck)
        deck.toggle_class("visible")

    def action_kill_switch(self) -> None:
        self.log_event("🛑 KILL SWITCH ACTIVATED via Keyboard Shortcut")

    def log_event(self, message: str) -> None:
        log = self.query_one("#syslog", Log)
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        log.write_line(f"{timestamp} {message}")

if __name__ == "__main__":
    app = CalamumConsole()
    app.run()
