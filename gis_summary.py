#*****************************************************************************
#
#  Project:  GIS Parcel Summary GP Service Script Tool
#  Purpose:  Custom, on-demand summary of all geographic features found on or
#            near a subject parcel. Creates an output pdf for the record.
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

import arcpy
import os
import datetime
import re
import sys
import traceback
from numpy import array, array_split

# ========== Parameters from ArcMap Script Tool ==========

# All layers/table views should be in the MXD and selected from the dropdown
# list. The mxd_file and legend_pdf should be on the server and accessed using
# a folder connection that uses the UNC path instead of a drive letter (i.e.,
# "\\server\map_docs" instead of "Y:\"

parcel = arcpy.GetParameterAsText(0)  # Text
parcel_layer = arcpy.GetParameterAsText(1)  # Feature Layer
solo_table = arcpy.GetParameterAsText(2)  # Table view
overlay_layer = arcpy.GetParameterAsText(3)  # Feature Layer
muni_layer = arcpy.GetParameterAsText(4)  # Feature Layer
annex_layer = arcpy.GetParameterAsText(5)  # Feature Layer
subdivision_layer = arcpy.GetParameterAsText(6)  # Feature Layer
legal_table = arcpy.GetParameterAsText(7)  # Table view
layers_raw = arcpy.GetParameterAsText(8).split(';')  # Multivalue Feature Layers
mxd_file = arcpy.GetParameterAsText(9)  # File, MXD with layers and layout
legend_pdf = arcpy.GetParameterAsText(10)  # File, P&Z produced legend and explanation
# Parameter 11 is output messages
# Parameter 12 is pdf out path

# When sharing service, parcel parameter should be User Defined Value, all
# others should be Constant Value.

# ========== Set up non-paramter variables ==========
start = datetime.datetime.now()

# Output messages
messages = []

try:
    solo_fields = ["parcel_number", "owner_name", "owner_address1",
                   "owner_address2", "owner_city_state_zip",
                   "property_address", "property_city", "acreage", "system_id"]
    parcel_fields = ["zone_primary", "zone_secondary"]
    legal_fields = ["system_id"]

    # Fudge factor for selections to ensure no nearby areas are missed
    buffer_distance = 100

    # For some reason, some layer names are surrounded by ' while others aren't
    layers_to_check = [ly.replace("'", "") for ly in layers_raw]

    # Set up text box variables
    # To set a text box to blank, you must pass " ". A simple "" (no space)
    # will error out when you try to set the .text property. These initial
    # values will only be overwritten later on if the values from the
    # table/feature class are not "".
    pnum = parcel
    date = datetime.datetime.today().strftime('Generated on %d %b. %Y at %I:%M %p')
    paddr = "(Not Available)"
    lac = "(Not Available)"
    oname = "(Not Available)"
    oaddr = "(Not Available)"
    czone = "(Not Available)"
    coverlay = " "
    jurisdiction = " "
    annex = " "
    legality = " "
    results1 = " "
    results2 = " "
    results3 = " "

    # Regex pattern for parcel IDs
    pattern = "[0-9]{2}-[0-9]{3}-[0-9]{4}"

    # 2006 Legality checks
    system_id = "unknown"  # system id linking current parcel to 2006 parcel
    exist_2006 = False  # Default to not existing as of Aug 8 2006

    # ========== Subject Parcel ==========
    # Make sure parcel number matches proper format
    # This should catch any SQL injection attacks, as any text that doesn't
    # match the parcel ID pattern will raise an exception
    if parcel and parcel != "#":
        if not re.match(pattern, parcel):
            raise ValueError("Parcel ID must be in the format YY-YYY-YYYY, where Y is a single digit number. For example, 06-019-0009.")

    # Select subject parcel
    where = "tax_id = '%s'" % (parcel)
    arcpy.SelectLayerByAttribute_management(parcel_layer, "NEW_SELECTION",
                                            where)

    # Make sure it's a real parcel
    parcel_count = int(arcpy.GetCount_management(parcel_layer).getOutput(0))
    if parcel_count < 1:
        raise ValueError("No parcel found with Parcel ID of {}".format(parcel))

    # ========== Solo Table Info ==========
    arcpy.AddMessage("Reading from solo table...")

    solo_where = "parcel_number = '%s'" % (parcel)
    with arcpy.da.SearchCursor(solo_table, solo_fields, solo_where) as solo_cursor:
        for row in solo_cursor:
            # Gracefully handle no-values ("None"s) from table, cast all to str
            # <Null> in table comes in as "None" type
            str_row = ["" if f is None else str(f) for f in row]
            if str_row[5] or str_row[6]:
                paddr = str_row[5] + "\r\n" + str_row[6]
            if str_row[7]:
                lac = str_row[7]
            if str_row[1]:
                oname = str_row[1]
            if str_row[2] or str_row[3] or str_row[4]:
                oaddr = str_row[2] + " " + str_row[3] + "\r\n" + str_row[4]
            if str_row[8]:
                system_id = str_row[8]
                # arcpy.AddMessage("system_id: {}".format(system_id))

    # ========== Legality Check ==========
    arcpy.AddMessage("Checking parcel legality...")

    # Subdivision check
    # Create centroid
    centroid_fc = "in_memory\\centroids"
    arcpy.Delete_management(centroid_fc)  # Just make sure it doesn't exist
    # arcpy.FeatureToPoint_management(parcel_layer, centroid_fc,
    #                                 point_location="INSIDE")

    # Because server-side arcpy licensing is... special...
    point = arcpy.da.FeatureClassToNumPyArray(parcel_layer, ["OID@", "SHAPE@XY"])
    SR = arcpy.Describe(parcel_layer).spatialReference
    arcpy.da.NumPyArrayToFeatureClass(point, centroid_fc, ['SHAPE@XY'], SR)

    # DQ CUP's out of subdivision layer
    cup_dq = "subdivision_location not like '% CUP%'"
    nocup_layer = "nocup_layer"
    arcpy.MakeFeatureLayer_management(subdivision_layer, nocup_layer, cup_dq)
    # select features from subdivision_layer that contain the centroid
    arcpy.SelectLayerByLocation_management(nocup_layer,
                                           "CONTAINS",
                                           centroid_fc,
                                           selection_type="NEW_SELECTION")
    # If count is > 0, potential subdivision
    subdivision_count = int(arcpy.GetCount_management(nocup_layer).getOutput(0))

    # 2006 check
    legal_where = "system_id = '%s'" % (system_id)
    results = [row for row in arcpy.da.SearchCursor(legal_table, legal_fields,
               legal_where)]
    if len(results) == 1:
        exist_2006 = True

    # Set legality variable
    if subdivision_count > 0:
        if exist_2006:
            legality = "Potentially a subdivision lot\r\nAppears to have the same configuration as on August 8, 2006"
        else:
            legality = "Potentially a subdivision lot\r\nDoes not appear to match its August 8, 2006 configuration"
    elif exist_2006:
        legality = "Legal parcel\r\nAppears to have the same configuration as on August 8, 2006"
    else:
        legality = "Restricted parcel\r\nDoes not appear to match its August 8, 2006 configuration"

    # ========== County Zoning Info From Feature Class ==========
    arcpy.AddMessage("Reading from parcel feature class...")

    with arcpy.da.SearchCursor(parcel_layer, parcel_fields, where) as parcel_cursor:
        for row in parcel_cursor:
            str_row = ["" if f is None else f for f in row]
            if str_row[1]:  # If there are two zones
                czone = str_row[0] + " / " + str_row[1]
            elif "CITY" in str_row[0]:
                czone = "Contact City for Zoning"
            elif str_row[0]:
                czone = str_row[0]

    # For the next four checks, we do a select by location to get the areas
    # that contain the subject parcel. We then check the number of selections-
    # if it's more than 0, we want the info. If it's 0, there is no
    # overlay/annex area/city/ sensitive area for that parcel.

    # ========== Overlay Zones ==========
    arcpy.AddMessage("Detecting Overlay zones...")

    arcpy.SelectLayerByLocation_management(overlay_layer, "WITHIN_A_DISTANCE",
                                           parcel_layer, 50, "NEW_SELECTION")
    selected_features = int(arcpy.GetCount_management(overlay_layer).getOutput(0))
    show_overlay = False
    # There are intersecting features if the count is more than 0
    if selected_features > 0:
        show_overlay = True
        overlays = []
        with arcpy.da.SearchCursor(overlay_layer, "name") as overlay_cursor:
            for row in overlay_cursor:
                if row[0] not in overlays:
                    overlays.append(row[0])
        coverlay = ", ".join(overlays)
    else:
        coverlay = "None"
    arcpy.SelectLayerByAttribute_management(overlay_layer, "CLEAR_SELECTION")

    # ========== Future Annexation Info ==========
    arcpy.AddMessage("Detecting Annexation Info...")
    arcpy.SelectLayerByLocation_management(annex_layer, "CONTAINS",
                                           parcel_layer,
                                           selection_type="NEW_SELECTION")
    # Additional selection to grab any parcels that cross boundaries
    arcpy.SelectLayerByLocation_management(annex_layer,
                                           "CROSSED_BY_THE_OUTLINE_OF",
                                           parcel_layer,
                                           selection_type="ADD_TO_SELECTION")
    annex_features = int(arcpy.GetCount_management(annex_layer).getOutput(0))
    # There are intersecting features if the count is more than 0
    if annex_features > 0:
        annex_areas = []
        with arcpy.da.SearchCursor(annex_layer, "annexation") as annex_cursor:
            for row in annex_cursor:
                if row[0] not in annex_areas:
                    annex_areas.append(row[0].title())
        annex = ", ".join(annex_areas)
    else:
        annex = "None Declared"
    arcpy.SelectLayerByAttribute_management(annex_layer, "CLEAR_SELECTION")

    # ========== Jurisdiction ==========
    # Do the jurisdiction check last to overwrite other fields that aren't
    # relevant in a city (zone, overlay)
    arcpy.AddMessage("Detecting Jurisdiction...")
    arcpy.SelectLayerByLocation_management(muni_layer, "CONTAINS",
                                           parcel_layer,
                                           selection_type="NEW_SELECTION")
    # Additional selection to grab any parcels that cross boundaries
    arcpy.SelectLayerByLocation_management(muni_layer,
                                           "CROSSED_BY_THE_OUTLINE_OF",
                                           parcel_layer,
                                           selection_type="ADD_TO_SELECTION")
    muni_features = int(arcpy.GetCount_management(muni_layer).getOutput(0))
    if muni_features > 0:
        with arcpy.da.SearchCursor(muni_layer, "name") as muni_cursor:
            for row in muni_cursor:
                jurisdiction = str(row[0]).title()

        # Overwrite fields not applicable to city parcels
        annex = "n/a"
        czone = "Contact %s for Zoning" % (jurisdiction)
        coverlay = "n/a"
        legality = "Incorporated Area\r\nContact %s for Applicable Regulations" % (jurisdiction)
    else:
        jurisdiction = "Cache County"
    arcpy.SelectLayerByAttribute_management(muni_layer, "CLEAR_SELECTION")

    # ========== Sensitive Areas Check ==========
    found_layers = []
    # Select features from the sensitve features layers that are within
    # buffer_distance feet of the target parcel (to account for parcel boundary
    # ambiguity)
    # If found, add to list of layers to be mapped
    for layer in layers_to_check:
        loop_start = datetime.datetime.now()
        arcpy.SelectLayerByLocation_management(layer, "WITHIN_A_DISTANCE",
                                               parcel_layer, buffer_distance,
                                               "NEW_SELECTION")
        selected_features = int(arcpy.GetCount_management(layer).getOutput(0))

        # There are intersecting features if the count is more than 0
        if selected_features > 0:
            found_layers.append(layer)

        # Clear the selection to prevent highlighted features in map
        arcpy.SelectLayerByAttribute_management(layer, "CLEAR_SELECTION")

        loop_end = datetime.datetime.now()
        time_delta = str(loop_end - loop_start)
        arcpy.AddMessage("%s took %s" % (layer, time_delta))

    # Trim service name from beginning of layer name
    trimmed_layers = [l.rpartition('\\')[2] for l in found_layers]

    # ========== Create additional analysis areas text ==========
    if len(trimmed_layers) > 0:

        # Split list into three columns
        # Uses numpy.array, numpy.array_split to evenly split into 3 columns
        layers_array = array(trimmed_layers)
        splits = array_split(layers_array, 3)
        fl1 = splits[0]
        fl2 = splits[1]
        fl3 = splits[2]

        # Create string for each column. All newlines must have '\r\n'.
        # Set strings to be empty to avoid leading whitespace
        results1 = ""
        results2 = ""
        results3 = ""

        # First column
        for l in fl1:
            layer_results = l + "\r\n"
            results1 += layer_results

        # Second column
        # If columns are empty, strings must be set to " " to show up as blank
        if len(fl2) > 0:
            for l in fl2:
                layer_results = l + "\r\n"
                results2 += layer_results
        else:
            results2 = " "

        # Third column
        if len(fl3) > 0:
            for l in fl3:
                layer_results = l + "\r\n"
                results3 += layer_results
        else:
            results3 = " "

    else:
        results1 = "No areas requiring further analysis were found on, or within %d feet of, parcel %s." % (buffer_distance, parcel)

    # ========== Set up map document ==========
    mxd = arcpy.mapping.MapDocument(mxd_file)
    df = arcpy.mapping.ListDataFrames(mxd)[0]
    layers = arcpy.mapping.ListLayers(mxd)

    # Populate text boxes
    # Checks the text box's .text property to find the right textbox. In ArcMap
    # layout view, set the location and size of the appropriate box and then
    # set it's text to match these strings.
    text_boxes = arcpy.mapping.ListLayoutElements(mxd, "TEXT_ELEMENT")
    for box in text_boxes:
        if box.text == "pnum":
            box.text = pnum
        elif box.text == "date":
            box.text = date
        elif box.text == "paddr":
            box.text = paddr
        elif box.text == "lac":
            box.text = lac
        elif box.text == "oname":
            box.text = oname
        elif box.text == "oaddr":
            box.text = oaddr
        elif box.text == "czone":
            box.text = czone
        elif box.text == "jurisdiction":
            box.text = jurisdiction
        elif box.text == "annex":
            box.text = annex
        elif box.text == "coverlay":
            box.text = coverlay
        elif box.text == "legality":
            box.text = legality
        elif box.text == "Results1":
            box.text = results1
        elif box.text == "Results2":
            box.text = results2
        elif box.text == "Results3":
            box.text = results3

    # Turn on applicable layers and get references for certain layers
    for l in layers:
        if l.name in trimmed_layers:
            l.visible = True
            arcpy.AddMessage("Turning on %s" % (l.name))
        elif l.name == "Parcels":
            p_layer = l
            l.visible = True
        elif l.name == "Selected Parcels":
            sp_layer = l
            l.visible = True
        elif l.name == "Roads":
            l.visible = True
        elif l.name == "Municipal Solid":
            l.visible = True
        elif l.name == overlay_layer.rpartition('\\')[2] and show_overlay:
            l.visible = True
        elif l.name == "Aerial":
            l.visible = True
        else:
            l.visible = False

    # Set definition query on selected parcel layer
    sp_layer.definitionQuery = where

    # Set extent
    df.extent = sp_layer.getExtent()  # Set extent to match selected parcel
    df.scale *= 1.1  # set scale to 110% to view vicinity

    # Clear selection to avoid feature selection highlights in the map
    arcpy.SelectLayerByAttribute_management(p_layer, "CLEAR_SELECTION")
    arcpy.SelectLayerByAttribute_management(parcel_layer, "CLEAR_SELECTION")

    # Create summary pdf
    out_path = os.path.join(arcpy.env.scratchFolder,
                            parcel + " Parcel Summary.pdf")
    arcpy.mapping.ExportToPDF(mxd, out_path)

    # Append legend to pdf
    pdf_doc = arcpy.mapping.PDFDocumentOpen(out_path)
    pdf_doc.appendPages(legend_pdf)
    pdf_doc.saveAndClose()
    del pdf_doc

    # Return pdf
    arcpy.SetParameter(12, out_path)

    messages.append("Click the link below to download the parcel summary")

    del mxd

except arcpy.ExecuteError:
    # Log the errors as warnings on the server (adding as errors would cause
    # the task to fail)
    arcpy.AddWarning(arcpy.GetMessages(2))

    # Pass the exception message to the user
    messages.append("ERROR: ")
    messages.append(arcpy.GetMessages(2))

    # Use a bad link for the output pdf
    arcpy.SetParameter(12, "Error")

except ValueError as ve:
    # Get the traceback object
    tb = sys.exc_info()[2]
    tbinfo = traceback.format_tb(tb)[0]

    # Concatenate information together concerning the error into a message
    # string
    pymsg = "PYTHON ERRORS:\nTraceback info:\n" + tbinfo + "\nError Info:\n" + str(sys.exc_info()[1])
    msgs = "\nArcPy ERRORS:\n" + arcpy.GetMessages(2) + "\n"

    # Log the errors as warnings on the server (adding as errors would cause
    # the task to fail)
    arcpy.AddWarning(pymsg)
    arcpy.AddWarning(msgs)

    # Tell the user to use a valid Parcel ID
    messages.append("ERROR: ")
    messages.append(ve.args[0])

    # Use a bad link for the output pdf
    arcpy.SetParameter(12, "Please fix Parcel ID and run tool again")

except Exception as e:
    # Get the traceback object
    tb = sys.exc_info()[2]
    tbinfo = traceback.format_tb(tb)[0]

    # Concatenate information together concerning the error into a message
    # string
    pymsg = "PYTHON ERRORS:\nTraceback info:\n" + tbinfo + "\nError Info:\n" + str(sys.exc_info()[1])
    msgs = "\nArcPy ERRORS:\n" + arcpy.GetMessages(2) + "\n"

    # Log the errors as warnings on the server (adding as errors would cause
    # the task to fail)
    arcpy.AddWarning(pymsg)
    arcpy.AddWarning(msgs)

    # Pass the exception message to the user
    messages.append(e.args[0])

    # Use a bad link for the output pdf
    arcpy.SetParameter(12, "ERROR")

finally:
    output_string = "\n".join(messages)
    arcpy.SetParameterAsText(11, output_string)
