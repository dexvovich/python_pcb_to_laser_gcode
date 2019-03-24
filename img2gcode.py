#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os, sys, cv2, numpy, argparse

"""
Description: Simple adjustable script to convert images of PCB's into GCode for laser engraver.

Author: Volodymyr Nazarenko, dex.tracers@gmail.com

License: GNU General Public License v3.0

Limitations: Lines that equal to laser dot size will disappear
"""

# -------------- USER definitions to be edited ----------
# default laser dot size in mm
laser_mm = 0.1

# laser-on / laser-off codes
laser_on = "M106 S1"
laser_off = "M107"

# GCode header / footer
gcode_header = '''M107 ; disable FAN
M106 L1 S0 ; switch FAN from PWM to On/Off mode (require Marlin code change)
M107       ; disable Laser
G90        ; use absolute positioning
G21        ; use mm
G92 X0     ; set current X position as 0
G92 Y0     ; set current Y position as 0
'''

gcode_footer = '''M107 ; disable laser
M106 L0 S0 ; switch FAN from On/Off to PWM mode (require Marlin code change)
M107       ; disable FAN
G0 X0 Y0   ; go to initial home X and Y
M84        ; disable steppers
M0         ; unconditional stop of printer
'''

# -------------- End of USER definitions ----------

# -------------- Arguments parsing, verification, internal common calculations ----------
# user arguments definitions
parser = argparse.ArgumentParser(description='Converting image to GCode for laser engraving')
parser.add_argument('--image',       dest='image_filename', help='Image filename / file path',                        type=str,   required=True)
parser.add_argument('--image_x_mm',  dest='image_x_mm',     help='Image width in mm',                                 type=float, required=True)
parser.add_argument('--image_y_mm',  dest='image_y_mm',     help='Image height in mm',                                type=float, required=True)
parser.add_argument('--gcode',       dest='gcode_filename', help='GCode filename / file path to store to',            type=str,   required=True)
parser.add_argument('--laser_mm',    dest='laser_mm',       help='Laser dot size in mm (%fmm is default)' % laser_mm, type=float, required=False, default=laser_mm)
parser.add_argument('--vector_mode', dest='vector_mode',    help='Switching between Vector (1) and Linear modes (0)', type=int,   required=False, default=0)
args = parser.parse_args()

# checking if image is compatible etc
try:
    # checking if file exists, opening the image
    os.path.getsize(args.image_filename)
    image_original = cv2.imread(args.image_filename)
    if image_original is None:
        raise Exception("Not a valid image file was provided")
    # getting image dimentions and converting it to greyscale (Y, X, not interesting)
    image_original_size = image_original.shape
    image_original_grey = cv2.cvtColor(image_original, cv2.COLOR_BGR2GRAY)
    # searching the borders of shapes and contours of them.
    # contours_main is array of all available shapes external contours, hierarchy_main is dependencies list between them
    thresh_original = cv2.threshold(image_original_grey, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    contours_main, hierarchy_main = cv2.findContours(thresh_original, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
except (IOError, OSError):
    print("Specified image file not exist")
    sys.exit(1)
except Exception as e:
    print(e.message)
    sys.exit(1)

# mm_per_dot_x and mm_per_dot_y is how many mm is presented by a single pixel on specific axis
mm_per_dot_x = float(args.image_x_mm / image_original_size[1])
mm_per_dot_y = float(args.image_y_mm / image_original_size[0])

# image_y_estimated and image_y_estimated stansd for proportioning check of provided image size
image_x_estimated = float(image_original_size[1] * mm_per_dot_y)
image_y_estimated = float(image_original_size[0] * mm_per_dot_x)

# checking if provided image sizes are correct. It's extremely important since image could be deformed in case of mistake
if mm_per_dot_x != mm_per_dot_y:
    print("You've specified incorrect size of image since calculated DPI is not proportional")
    print("Image size in pixels is:\n X: %i\n Y: %i\n" % (image_original_size[1], image_original_size[0]))
    print("X dimension provided as %fmm, estimated value based on Y size and dimension is, mm: %f" % (args.image_x_mm, image_x_estimated))
    print("Y dimension provided as %fmm, estimated value based on X size and dimension is, mm: %f" % (args.image_y_mm, image_y_estimated))
    print("Please choose one of proposed estimated values for corresponding axis to fix proportioning of image")
    exit(1)

# proportional check passed - using singe-axis value as our pixel dimention, since it's equal over image for both X and Y
mm_per_dot = mm_per_dot_x

# dots_per_laser is amount of dot's which will be filled-up by laser beam.
# is used to build internal fill of identified shapes - could be a bit lesser than real, will increase quality
dots_per_laser = int(round(args.laser_mm / mm_per_dot))

# dots_per_laser_outer_edge is amount of dots which will be filled-up by half of laser beam
# is used to build outer-edge for the initial identified shapes borders generation.
# MUST be real or a bit bigger value to omit problems with objets that are closer than 2*laser_mm
# +0.5 in order to trigger round-up in case if fractional value is > 0.5
dots_per_laser_outer_edge = int(round((args.laser_mm / mm_per_dot / 2.0) + 0.5))

# -------------- End of arguments parsing, verification, internal common calculations ----------


# -------------- Reporting that all OK and we could proceed with provided parameters ----------
print("Working with image: %s" % args.image_filename)
print("Size of image, X Y, px: %i %i" % (image_original_size[1], image_original_size[0]))
print("Size of image, mm: %.2f %.2f" % (args.image_x_mm, args.image_y_mm))
print("Thickness of laser, mm: %f" % args.laser_mm)
print("Thickness of laser to be used for internal shape fill, px: %i" % dots_per_laser)
print("Thickness of shapes body that will be removed from outer edge of each shape, px: %i" % dots_per_laser_outer_edge)
print("Contours found: %i" % len(contours_main))
#  -------------- End of reporting ----------

# Opening gcode file in write mode, writing a header
gcode_file = open(args.gcode_filename,"w")
gcode_file.write(gcode_header)

if (args.vector_mode == 0):
    # -------------- Vector laser track searching ----------
    # algorithm of laser tracks generation is following:
    # 1. removing the outer edge of the shapes.
    #    if this is not done - laser will make each border of the shapes laser_mm/2 mm larger than planned
    #    after border removal - we have initial image to search contours on
    # 2. in the loop:
    #     - searching for a shape contours on initial image
    #     - adding the ones that were found to the shapes[shape_number] list as the laser track
    #     - drawing a white borders on initial image with dots_per_laser thickness according to contour
    # 3. once loop is finished - in shapes we have all identified contours
    
    print("Working in Vector mode")

    shapes = []
    main_contour_index = 0
    for contour in contours_main:
        # holder of main contour internal contours
        paths_tmp = []

        # checking if this is internal closing contour of any of external contours. If yes - no need to handle it.
        if (hierarchy_main[0][main_contour_index][3] > -1):
            main_contour_index+=1
            continue

        # creating blank image for our shape
        main_contour_img_tmp = numpy.zeros([image_original_size[0], image_original_size[1]]).astype(numpy.uint8)
        main_contour_img_tmp.fill(255)

        # drawing the main contour fully filled inside in order to present our main shape
        cv2.drawContours(main_contour_img_tmp, [contour], -1, (0,0,0), -1)

        # if contour has closing contour (for example - it's rounding ground or has holes) - drawing it with all internals emptied properly
        if (hierarchy_main[0][main_contour_index][2] > -1):
            next_main_subcontour = hierarchy_main[0][main_contour_index][2]
            cv2.drawContours(main_contour_img_tmp, contours_main, next_main_subcontour, (255,255,255), -1)
            while next_main_subcontour > -1:
                cv2.drawContours(main_contour_img_tmp, contours_main, next_main_subcontour, (255,255,255), -2)
                next_main_subcontour = hierarchy_main[0][next_main_subcontour][0]

        # removing outer border of half laser size to determine first needed track over shape
        cv2.drawContours(main_contour_img_tmp, [contour], -1, (255,255,255), dots_per_laser_outer_edge)

        # in a loop - creating laser track, applying laser job to the image and searching for contours again
        while True:
            tmp_thresh = cv2.threshold(main_contour_img_tmp, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
            tmp_contours = cv2.findContours(tmp_thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]
            if not len(tmp_contours):
                break

            # in case if we've found contours - adding them as laser tracks and applying to the shape image
            paths_tmp.append(tmp_contours)
            cv2.drawContours(main_contour_img_tmp, tmp_contours, -1, (255,255,255), dots_per_laser)

        # In case if all was OK - adding our collected laser tracks to main array
        if len(paths_tmp):
            shapes.append(paths_tmp)

        # incrementing main contour counter
        main_contour_index += 1
    # -------------- End of vector laser track searching ----------

    # -------------- GCode generation based on vector tracks ----------
    # algorithm of gcode generation is following:
    # 1. adding header
    # 2. going over the shapes one-by-one and converting pixels positions to mm positions
    # 3. writing the mm positions to gcode file
    # 3. adding footer

    # going over identified shapes
    for shape in shapes:
        # last_dot indicating last place where laser was
        latest_dot = [[0, 0]]
        # going over contour-searching steps that were made
        for steps in shape:
            # going over the tracks identified in one contour-search step (could be multiple contours if shape splitted)
            for track in steps:
                first_dot = track[0][0]
                # Now walking over all points of track
                for dot in track:
                    # checking if this is the near jump from the previous track of the same shape.
                    near_laser_jump = ((abs(dot[0][0] - latest_dot[0][0]) <= dots_per_laser) and ((abs(dot[0][1] - latest_dot[0][1]) <= dots_per_laser)))

                    # checking if this is the first point of track
                    if (dot[0][0] == first_dot[0]) and (dot[0][1] == first_dot[1]):
                        # if far jump - disabling laser since we're going to changed the shape
                        if not near_laser_jump:
                            gcode_file.write("%s \n" % laser_off)

                        # going to the start point
                        gcode_file.write("G1 X%.2f Y%.2f F1500\n" % ((dot[0][0] * mm_per_dot), (dot[0][1] * mm_per_dot)))

                        # if far jump - enabling laser after start point was reached
                        if not near_laser_jump:
                            gcode_file.write("%s \n" % laser_on)

                    # if not the first poinit - just moving to it, nothing more to be done
                    else:
                        gcode_file.write("G1 X%.2f Y%.2f F900\n" % ((dot[0][0] * mm_per_dot), (dot[0][1] * mm_per_dot)))

                    # storing current dot as the latest one
                    latest_dot = dot

                # Returning to initial startpoint of the track in case if it is not straight line and if distance is more than 2*laserdot between any of axis
                if (len(track) > 2) and ((abs(track[0][0][0] - dot[0][0]) > dots_per_laser * 2) or (abs(track[0][0][1] - dot[0][1]) > dots_per_laser * 2)):
                    gcode_file.write("G1 X%.2f Y%.2f F900\n" % ((track[0][0][0] * mm_per_dot), (track[0][0][1] * mm_per_dot)))

                    # storing current dot as the latest one
                    latest_dot = track[0]
else:
    # -------------- Linear laser track searching ----------
    print("Working in Linear mode")

    # TODO: this mode pending refactoring
    # going over all lines (Y) one by one and searching if there's something we should print
    data_lines = {}
    line = 0
    while line < image_original_size[0]:
        line_data = [image_original_grey[line, column] for column in range(0, image_original_size[1], dots_per_laser)]
        if line_data.count(255):
            data_lines[line]=[]
        line+=dots_per_laser

    # going over all columns (X) one by one and searching where's something we should print
    for line in data_lines.keys():
        line_start = 0
        column = 0
        while column < image_original_size[1]:
            point_color = image_original_grey[line, column]
            if point_color == 0 and line_start == 0:
                line_start = column
            if point_color == 255 and line_start > 0:
                data_lines[line].append([line_start, column])
                line_start = 0
            column+=dots_per_laser

    # inverting to let the laser go as a snake
    inverted = False
    for line in sorted(data_lines.keys()):
        tracks = data_lines[line]
        tracks_passed = 0
        tracks_available = len(tracks)
        while tracks_passed < tracks_available:
            if inverted:
                track = tracks[tracks_available - tracks_passed - 1]
                gcode_file.write("G1 X%.2f00 Y%.2f00 F1500\n" % ((track[1] * mm_per_dot), (line * mm_per_dot)))
                gcode_file.write("M106 S1 \n")
                gcode_file.write("G1 X%.2f00 Y%.2f00 F900 \n" % ((track[0] * mm_per_dot), (line * mm_per_dot)))
                gcode_file.write("M107 \n")
            else:
                track = tracks[tracks_passed]
                gcode_file.write("G1 X%.2f00 Y%.2f00 F1500\n" % ((track[0] * mm_per_dot), (line * mm_per_dot)))
                gcode_file.write("M106 S1 \n")
                gcode_file.write("G1 X%.2f00 Y%.2f00 F900 \n" % ((track[1] * mm_per_dot), (line * mm_per_dot)))
                gcode_file.write("M107 \n")
            tracks_passed+=1
        inverted = not inverted
    # -------------- End of linear laser track searching ----------

# writing GCode footer and closing a file
gcode_file.write(gcode_footer)
gcode_file.close()

print("\n\nGcode file generated: %s" % args.gcode_filename)
