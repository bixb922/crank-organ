# Introduction to RC Servos

RC (Radio Control) servos are compact actuators commonly used in robotics, model aircraft, and other hobbyist applications. They are designed to precisely control angular position, making them ideal for tasks such as steering, controlling flaps, or moving robotic joints.

Control:

RC servos are typically controlled using Pulse Width Modulation (PWM). 
A control signal is sent to the servo, where the width of the pulse determines the target position of the servo arm (horn). The standard pulse width ranges from about 1 ms (minimum position) to 2 ms (maximum position), with a repetition rate of 50 Hz (20 ms period). The duty cycle is the ratio of the pulse width to the total period.

Speed:

The speed of a servo refers to how quickly it can move from one position to another. This is usually specified as the time required to rotate 60° at a given voltage (e.g., 0.12 seconds/60° at 6V). Faster servos are used for applications requiring quick response.

Force (Torque):

Servos are rated by their torque, which is the rotational force they can apply, typically measured in kg·cm or oz·in. Higher torque servos can move heavier loads or resist greater external forces. The force is highest if the horn is held in place. The current here is also the highest (stall current). See the specs for force or torque when stalling. 1 kg/cm or higher is a common figure.

Horns:

The servo horn is the output arm attached to the servo shaft. It transmits the servo's motion to the mechanical system being controlled. Horns come in various shapes and sizes to suit different applications.

Digital and analog RC servos:

Originally the RC servos had an analog circuit, many modern servos have a digital circuit (i.e. based on a very small microcomputer). The SG90 is an analog servo.

There are some advantages/disadvantages for analog vs digital. I'd use digital servos since they could have a better response time.

Connections:

RC servos normally have a connector with 3 wires: black for ground, red for supply voltage and yellow for signal.

For digital servos, the signal can be connected directly to a GPIO output of the ESP32-S3, if defined as a servo output in the software. It is best to put a 220 Ohm resistor in series of this connection, i.e. GPIO output to resistor then to RC input.

The supply voltage depends of the servo. Fast servos may need 7.4V or more. The servo has it's own circuit inside to amplify the GPIO or PCA9685 output to suitable currents to move the motor inside the servo.

Summary:

- RC servos are controlled by PWM signals (pulse width determines position).
- Speed and torque are key performance characteristics.
- Servo horns connect the servo to the mechanism being actuated.

# 0. Selecting an appropriate servo to move a crank organ valve

The force (torque) that a servo can supply is normally more than enough to move a crank organ valve. Bass valves at higher pressures may need a force of 1 Newton to open (1 Newton lifts about 100g). A small servo can lift 500g at least.

The main issue with servos is speed. One of the most common (and cheap) RC servos is the SG90:

>>>>> picture

The speed is  0.1 to 0.15 seconds to rotate 60° depending on what the vendor says on its site. It has plastic gears, so it the gears may get damaged if it stalls or exerts too much force.

However, an angle of much less than 60° is needed to open a valve. The aperture of a valve is normally about 3 or 4 mm maximum. With a horn of 2.5 cm, that means an angle of 10°. If a fast servo moves at 0.06 seconds/60°, in theory 10° takes only 0.01 seconds. In practice, that relation does not hold so well, even small movements can take their time.

However, a fast digital servo of say 0.06 seconds/60° will open/close a valve allowing notes of 30 milliseconds followed by 30 milliseconds of pause.

That should be enough for crank organ music, and is similar or even faster than what a paper roll or book allows.

Solenoid valves are faster than that. See for example this article here: http://www.fonema.se/valvetime/valvetime.html

Solenoid valves open and close normally within 5 milliseconds. That is probably several times faster than a RC servo. But on the other hand, the opening/closing of valves on a paper roll organ isn't that fast either. 

The final word is not the physics and measurements, but what you hear and the musical effect. So if you try out a servo, buy one and test it.

# 1. Parameters for servo motors

Instead of a 50 Hz (= 20 millisecond = 20000 microseconds) refresh rate, it is advisable to lower the rate to get faster response. The refresh period should not go below 3 or 4 milliseconds, so a proposed period is 5000 microseconds. This period should be set the same for all servos. There seems to be no need to vary it (although you can set different periods for each PCA9685 or for the GPIO servo outputs).

A pulse width of 1000 microseconds normally means 0° angle and 2000 microseconds means 180° angle. Some servos have other definitions, for example some go between 500 microseconds and 2500 microseconds. See the servo's specifications.

The software accepts pulse widths from 1000 to 2000, since normally a small angle variation is needed. The Pinout and MIDI configuration will show the conversion of pulse width to angle when you alter the pulse width.

The angles can be defined for groups of MIDI outputs or even for each MIDI output. Altering this will need you to edit the pinout.json file directly, inserting "servopulse" directives where needed.

The software calculates the duty cycle for PWM.

