class ApcButtonRange:
    PushButton = (0, 63)
    BottomSide = (64, 71)
    RightSide = (82, 89)
    Shift = (98, 98)
    Faders = (48, 56)


class ApcSideButtonColor:
    Off = 0
    On = 1
    Blink = 2


class ApcPushButtonColor:
    Off = 0
    Green = 1
    GreenBlink = 2
    Red = 3
    RedBlink = 4
    Yellow = 5
    YellowBlink = 6


def note_in_range(note: int, button_range: (int, int)) -> bool:
    return button_range[0] <= note <= button_range[1]
