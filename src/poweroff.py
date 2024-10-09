# (c) 2023 Hermann Paul von Borries
# MIT License
# Power off task. Monitors activity and enters deepsleep to save battery
# if not active.
import machine
import asyncio

from player import player
from minilog import getLogger
from config import config
from led import led
from solenoid import solenoids
from setlist import setlist
import webserver


class PowerManager:
    def __init__(self):
        self.logger = getLogger(__name__)
        self.power_task = asyncio.create_task(self._power_process())
        self.logger.debug("init ok")

    async def _power_process(self):
        last_tune = None
        last_playtime = None
        idle_minutes = 0
        idle_deepsleep_minutes = config.get_int("idle_deepsleep_minutes", 15)
        try:
            while True:
                await asyncio.sleep(60)  # Sleep for 1 minute and check.

                progress = player.get_progress()
                playtime = progress["playtime"]
                tune = progress["tune"]
                # Any activity in the last minute?
                if (
                    playtime != last_playtime
                    or tune != last_tune
                    or webserver.is_active()
                ):
                    # Yes, reset time
                    idle_minutes = 0
                else:
                    idle_minutes += 1
                    self.logger.debug(
                        f"Idle for {idle_minutes} minutes limit {idle_deepsleep_minutes}"
                    )

                last_tune = tune
                last_playtime = playtime

                if idle_minutes > idle_deepsleep_minutes:
                    self.logger.info(
                        f"Idle for {idle_minutes} minutes, entering deepsleep"
                    )
                    led.ack()
                    await self.wait_and_power_off()
                    # Not to return

        except Exception as e:
            self.logger.exc(e, "power management process aborted")

    async def wait_and_power_off(self):
        setlist.stop_tune()
        solenoids.all_notes_off()
        # Wait for web server to respond, led to flash, etc
        await asyncio.sleep_ms(1000)
        solenoids.all_notes_off()
        led.off()
        # Closest thing to self power off.
        machine.deepsleep()

    async def wait_and_reset(self):
        setlist.stop_tune()
        # Wait for web server to respond, led to flash, etc
        await asyncio.sleep_ms(1000)
        solenoids.all_notes_off()
        led.off()
        machine.reset()

poweroff = PowerManager()
