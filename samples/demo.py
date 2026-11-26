"""Run the original workday demo and the replacement drill in one entry point."""
from samples import replacement_drill, workday


def main() -> None:
    workday.main()
    replacement_drill.main()


if __name__ == '__main__':
    main()
