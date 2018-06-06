#*****************************************************************************
#
#  Project:  Address to Precinct Analysis Tool
#  Purpose:  Determine voting precinct for a given address
#  Author:   Jacob Adams, jacob.adams@cachecounty.org
#
#*****************************************************************************
# MIT License
#
# Copyright (c) 2018 Cache County
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#*****************************************************************************

# !!!!!!
#
# NOTE!
#
# This tool has not been tested extensively and should not be relied on for
# official voting info. It is completely dependent on the accuracy of the
# address locator(s) used and the accuracy of the precinct feature class.
#
# !!!!!!

import arcpy
import os
import sys
import traceback

# ========== Parameters from ArcMap Script Tool ==========
address = arcpy.GetParameterAsText(0)  # Text
locator = arcpy.GetParameterAsText(1)  # Address Locator Service
precinct_layer = arcpy.GetParameterAsText(2)  # Feature Layer
precinct_field = arcpy.GetParameterAsText(3)  # Field
# Parameter 4 is precinct ID
# Parameter 5 is geocoded point x/y
# Parameter 6 is output messages
# Parameter 7 is error messages

# When sharing service, address parameter should be User Defined Value, all
# others should be Constant Value.

# ========== Set up non-paramter variables ==========
address_point_fc = "in_memory\\address_point"
address_point_layer = "address_point_layer"
scratch_table = os.path.join(arcpy.env.scratchGDB, "addr_table")
#scratch_table = "in_memory\\addr_table"
addr_table_view = "addr_table_view"
address_field = "address"

# Precinct to be returned
precinct = ''

# Geocodded x/y point in WGS84
xy = ()

# Output messages
match_info = ''
errors = []

# Clean up in_memory for safety
arcpy.Delete_management("in_memory")

try:
    # We have to use the scratch gdb because ArcGIS tries to copy over the
    # in_memory table for whatever reason, then proceeds to append records to
    # it instead of overwriting it every time. Using the gdb introduces several
    # disk accesses that probably slow it down a little bit, but it shouldn't
    # be too unbearable.

    # Delete the old table.
    if arcpy.Exists(scratch_table):
        arcpy.Delete_management(scratch_table)

    # Create the table and associated view to hold the address
    arcpy.CreateTable_management(arcpy.env.scratchGDB, "addr_table")
    arcpy.MakeTableView_management(scratch_table, addr_table_view)

    # Add the address field and copy the address to the table
    arcpy.AddField_management(addr_table_view, address_field, "TEXT", 200)
    with arcpy.da.InsertCursor(addr_table_view, address_field) as ic:
        ic.insertRow((address,))

    # Geocode the address
    arcpy.GeocodeAddresses_geocoding(addr_table_view, locator, "'Single Line Input' {} VISIBLE NONE".format(address_field), address_point_fc)

    # Make sure we have a match, translate point to Web Mercator
    arcpy.MakeFeatureLayer_management(address_point_fc, address_point_layer)
    with arcpy.da.SearchCursor(address_point_layer, ["Status", "SHAPE@XY", "SHAPE@"]) as point_sc:
        for row in point_sc:
            match_info = "Type: {}, Location: {}".format(row[0], str(row[1]))
            if row[0] not in ['M', 'T']:
                raise ValueError("Address not found: {}".format(address))

            # If it is a valid match, translate to web mercator
            web_point = row[2].projectAs(arcpy.SpatialReference(3857))
            xy = (web_point.centroid.X, web_point.centroid.Y)

    # Select Precinct
    arcpy.SelectLayerByLocation_management(precinct_layer, "CONTAINS",
                                           address_point_layer, 0,
                                           "NEW_SELECTION")

    # Make sure we have just one precinct
    precinct_count = int(arcpy.GetCount_management(precinct_layer).getOutput(0))
    if precinct_count != 1:
        raise ValueError("No precincts found.")

    # Get precinct ID and return
    with arcpy.da.SearchCursor(precinct_layer, precinct_field) as sc:
        for row in sc:
            precinct = row[0]

    arcpy.SetParameterAsText(4, precinct)

# Arcpy error handling
except arcpy.ExecuteError:
    # Log the errors as warnings on the server (adding as errors would cause the task to fail)
    arcpy.AddWarning(arcpy.GetMessages(2))

    # Pass the exception message to the user
    errors.append("ERROR")
    errors.append(arcpy.GetMessages(2))

    # Return an error instead of a precinct code
    arcpy.SetParameter(4, "Error")

# ValueErrors are thrown in several places as sanity checks
except ValueError as ve:
    # Get the traceback object
    tb = sys.exc_info()[2]
    tbinfo = traceback.format_tb(tb)[0]

    # Concatenate information together concerning the error into a message string
    pymsg = "PYTHON ERRORS:\nTraceback info:\n" + tbinfo + "\nError Info:\n" + str(sys.exc_info()[1])
    msgs = "\nArcPy ERRORS:\n" + arcpy.GetMessages(2) + "\n"

    # Log the errors as warnings on the server (adding as errors would cause the task to fail)
    arcpy.AddWarning(pymsg)
    arcpy.AddWarning(msgs)

    # Tell the user to use a valid Parcel ID
    errors.append("ERROR")
    errors.append(ve.args[0])

    # Return an error instead of a precinct code
    arcpy.SetParameter(4, "Error")

# And any other errors
except Exception as e:
    # Get the traceback object
    tb = sys.exc_info()[2]
    tbinfo = traceback.format_tb(tb)[0]

    # Concatenate information together concerning the error into a message string
    pymsg = "PYTHON ERRORS:\nTraceback info:\n" + tbinfo + "\nError Info:\n" + str(sys.exc_info()[1])
    msgs = "\nArcPy ERRORS:\n" + arcpy.GetMessages(2) + "\n"

    # Log the errors as warnings on the server (adding as errors would cause the task to fail)
    arcpy.AddWarning(pymsg)
    arcpy.AddWarning(msgs)

    # Pass the exception message to the user
    errors.append(e.args[0])

    # Return an error instead of a precinct code
    arcpy.SetParameter(4, "Error")

# Set all the output parameters
finally:
    arcpy.SetParameterAsText(5, str(xy))
    arcpy.SetParameterAsText(6, match_info)
    error_string = '---'.join(errors)
    arcpy.SetParameterAsText(7, error_string)
