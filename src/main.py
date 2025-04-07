from sys import argv, exit

from src.afkclicker import AfkClicker


def main():
    clicker = AfkClicker()
    clicker.run()
    exit(1)


if __name__ == "__main__":
    main()
