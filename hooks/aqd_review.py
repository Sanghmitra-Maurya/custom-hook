import keyboard
import time


def main():
    time.sleep(3)

    # Press Alt + Win + Q
    keyboard.press_and_release('alt+windows+q')

    time.sleep(5)

    keyboard.write("review workspace")
    keyboard.press_and_release('enter')


if __name__ == "__main__":
    main()