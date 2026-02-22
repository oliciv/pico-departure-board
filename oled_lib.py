import framebuf
from machine import Pin, SPI
import time

DC = 8
RST = 12
MOSI = 11
SCK = 10
CS = 9


class OLED_1inch3(framebuf.FrameBuffer):
    # https://www.waveshare.com/wiki/Pico-OLED-1.3
    def __init__(self, rotate=False):
        self.width = 128
        self.height = 64

        self.rotate = 0 if rotate else 180  # only 0 and 180

        self.cs = Pin(CS, Pin.OUT)
        self.rst = Pin(RST, Pin.OUT)

        self.cs(1)
        self.spi = SPI(1)
        self.spi = SPI(1, 2000_000)
        self.spi = SPI(
            1, 20000_000, polarity=0, phase=0, sck=Pin(SCK), mosi=Pin(MOSI), miso=None
        )
        self.dc = Pin(DC, Pin.OUT)
        self.dc(1)
        self.buffer = bytearray(self.height * self.width // 8)
        super().__init__(self.buffer, self.width, self.height, framebuf.MONO_HMSB)
        self.init_display()

        self.white = 0xFFFF
        self.black = 0x0000

    def write_cmd(self, cmd):
        self.cs(1)
        self.dc(0)
        self.cs(0)
        self.spi.write(bytearray([cmd]))
        self.cs(1)

    def write_data(self, buf):
        self.cs(1)
        self.dc(1)
        self.cs(0)
        self.spi.write(bytearray([buf]))
        self.cs(1)

    def init_display(self):
        """Initialize dispaly"""
        self.rst(1)
        time.sleep(0.001)
        self.rst(0)
        time.sleep(0.01)
        self.rst(1)

        self.write_cmd(0xAE)  # turn off OLED display

        self.write_cmd(0x00)  # set lower column address
        self.write_cmd(0x10)  # set higher column address

        self.write_cmd(0xB0)  # set page address

        self.write_cmd(0xDC)  # et display start line
        self.write_cmd(0x00)
        self.write_cmd(0x81)  # contract control
        self.write_cmd(0x6F)  # 128
        self.write_cmd(0x21)  # Set Memory addressing mode (0x20/0x21) #
        if self.rotate == 0:
            self.write_cmd(0xA0)  # set segment remap
        elif self.rotate == 180:
            self.write_cmd(0xA1)
        self.write_cmd(0xC0)  # Com scan direction
        self.write_cmd(0xA4)  # Disable Entire Display On (0xA4/0xA5)

        self.write_cmd(0xA6)  # normal / reverse
        self.write_cmd(0xA8)  # multiplex ratio
        self.write_cmd(0x3F)  # duty = 1/64

        self.write_cmd(0xD3)  # set display offset
        self.write_cmd(0x60)

        self.write_cmd(0xD5)  # set osc division
        self.write_cmd(0x41)

        self.write_cmd(0xD9)  # set pre-charge period
        self.write_cmd(0x22)

        self.write_cmd(0xDB)  # set vcomh
        self.write_cmd(0x35)

        self.write_cmd(0xAD)  # set charge pump enable
        self.write_cmd(0x8A)  # Set DC-DC enable (a=0:disable; a=1:enable)
        self.write_cmd(0xAF)

    def show(self):
        self.write_cmd(0xB0)
        for page in range(0, 64):
            if self.rotate == 0:
                self.column = 63 - page  # set segment remap
            elif self.rotate == 180:
                self.column = page

            self.write_cmd(0x00 + (self.column & 0x0F))
            self.write_cmd(0x10 + (self.column >> 4))
            for num in range(0, 16):
                self.write_data(self.buffer[page * 16 + num])
