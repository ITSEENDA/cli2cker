from sys import argv, exit

from afkclicker import AfkClicker


# from clickerhelper import ClickerHelper



def main():
    clicker = AfkClicker()
    clicker.run()
    exit(1)
    # # helper = ClickerHelper()
    # # helper.add_option('set', 'Change the value of one or multiple parameter', ['p', '-m', '-d', '-k', '-s'])
    # # helper.print_helper()


if __name__ == "__main__":
    main()
