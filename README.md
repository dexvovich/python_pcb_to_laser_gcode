## A set of python scripts to convert PCB into GCODE for laser engraving over photoresist or ink mask

### Includes scripts to:
  - Convert from PCB CAD software types to images (planned)
  - Convert from images to gcode (done)

### Supported features: 
  - Vector-based gcode generation (laser going XY over the shape's boarder from outer border to inside)
  - Linear-based gcode generarion (laser is going on X axis and drawing line-by-line like a matrix printer)
  - In vecor mode - shapes walked around to provide best result (not zigzag etc)
  - Outer border of shapes is decreased on the size of half of laser beam to not go out-of-shape-size
  - Closed / embedded shapes handled properly (polygons with holes, polygon inside of polygon, ground around PCB etc)
  - Personal GCodes for laser on/off, printer preparation and stop could be confiugred
  - Dual-speed support available - fast to move to first point of track, slow for laser engraving
  - All images are vectorized at the beginning in order to not rely on colours and to decrease shapes borders
  - Laser-off lag mitigation by using G4 command after M107 as "Laser-off" combination. (100ms by default)

### Known limitations: 
  - Line with thickness equal to laser dot size will disappear and will not be converted (0.1mm by default).
  - In Linear mode - walking over the Y axis is done with the step equal to laser beam size (0.1 mm by default)
  - Anet A8 is not able to properly work frequently with FAN and SD-CARD. Engraving could stuck. Use USB and direct gcode sender.

### Required additional python modules: 
  - OpenCV (cv2)
  - numpy

#### Usage example: img2gcode.py --image 123.png --image_x_mm 100 --image_y_mm 100 --gcode 123.gcode

Arguments supported:
  - -h, --help            show help message and exit
  - --image               Image filename / file path
  - --image_x_mm          Image width in mm
  - --image_y_mm          Image height in mm
  - --gcode               GCode filename / file path to store to
  - --laser_mm            Laser dot size in mm (0.100000mm is default)
  - --linear_mode         Work in Linear mode (0 = vector, 1 = linear, default is vector)
