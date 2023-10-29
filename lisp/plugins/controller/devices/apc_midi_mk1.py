class ApcMidiMk1Color:
    Off = 0

    Green = 1
    GreenBlink = 2
    Red = 3
    RedBlink = 4
    Yellow = 5
    YellowBlink = 6

    SimpleButtonOff = 0
    SimpleButtonOn = 1
    SimpleButtonBlink = 2


def map_color(note, color):
    if note < 64:
        return color
    else:
        return 0 if color == ApcMidiMk1Color.Off else color % 3 + 1
