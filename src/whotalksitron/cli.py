import click


@click.group()
@click.version_option(package_name="whotalksitron")
def main() -> None:
    """Audio transcription CLI with speaker identification."""


if __name__ == "__main__":
    main()
