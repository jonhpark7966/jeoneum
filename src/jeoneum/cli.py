"""jeoneum CLI (typer). See docs/spec.md §9."""
from __future__ import annotations

import typer

from .schema import Voice

app = typer.Typer(help="전음(傳音) — speaker-preserving multilingual dubbing.")


def _parse_voices(pairs: list[str] | None) -> dict[str, Voice]:
    out: dict[str, Voice] = {}
    for p in pairs or []:
        speaker, ref = p.split("=", 1)              # e.g. 0=my_voice.wav
        out[speaker] = Voice(mode="manual", ref_audio=ref)
    return out


@app.command()
def dub(
    source: str = typer.Argument(..., help="video/audio file, YouTube URL, or .srt/.json"),
    to: str = typer.Option(..., "--to", help="comma-separated target languages, e.g. en,ja"),
    out: str = typer.Option("out", "--out", "-o", help="output directory"),
    voice: list[str] = typer.Option(None, "--voice", help="manual speaker voice, e.g. 0=ref.wav"),
    keep_background: bool = typer.Option(True, "--keep-background/--replace-audio"),
    duck: bool = typer.Option(False, "--duck/--no-duck", help="duck background under voice (default off)"),
    duck_db: float = typer.Option(-12.0, "--duck-db", help="background attenuation while voice is active"),
    subs_translated: bool = typer.Option(False, "--subs-translated", help="input subs are already in target language"),
    max_speedup: float = typer.Option(1.3, "--max-speedup"),
):
    """Dub SOURCE into one or more target languages."""
    from .pipeline import dub as run_dub

    langs = [s.strip() for s in to.split(",") if s.strip()]
    outputs = run_dub(
        source, langs, out,
        subs_translated=subs_translated,
        keep_background=keep_background,
        manual_voices=_parse_voices(voice),
        max_speedup=max_speedup,
        duck=duck,
        duck_db=duck_db,
    )
    for lang, path in outputs.items():
        typer.echo(f"[{lang}] {path}")


@app.command()
def serve(host: str = "0.0.0.0", port: int = 7870):
    """Start the REST API + WebUI."""
    import uvicorn

    uvicorn.run("jeoneum.server:app", host=host, port=port)


if __name__ == "__main__":
    app()
