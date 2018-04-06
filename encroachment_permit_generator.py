#*****************************************************************************
# 
#  Project:  Python Encroachment Permit Generator GP Service Script Tool
#  Purpose:  Custom scripted permit generator displaying pertinent info from
#            encroachment feature class table; replaces old tool that uses 
#            dynamic text box fields in the mxd.
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
import sys
import traceback
#from numpy import array, array_split

# ========== Parameters from ArcMap Script Tool ==========

# All layers/table views should be in an MXD and selected from the dropdown
# list. The mxd_file should be on the server and accessed using a folder
# connection that uses the UNC path instead of a drive letter (i.e.,
# "\\server\map_docs" instead of "Y:\"

permit_layer = arcpy.GetParameterAsText(0)  # Feature Layer
permit_fields = arcpy.GetParameterAsText(1).split(';')  # Multivalue Fields, from permit_layer
permit_number = arcpy.GetParameterAsText(2)  # Text, hand-entered
mxd_file = arcpy.GetParameterAsText(3)  # File, MXD with layers and layout
# Parameter 4 is pdf out path
# Parameter 5 is error output string

messages = []

try:
    # Text box variables, must have a blank space to show up blank in mxd
    parcel_no = " "
    permit_no = " "
    fee = " "
    payment_type = " "
    receipt = " "
    contact = " "
    contractor = " "
    description = " "
    inspector_findings = " "

    # Set up where clause for singling out a permit
    where = "permit_num = '{}'".format(permit_number)

    with arcpy.da.SearchCursor(permit_layer, "permit_num",
                               where) as search_cursor:
        if sum(1 for _ in search_cursor) < 1:  # sums number of records
            raise ValueError("Cannot find permit {} in permit list.".format(
                permit_number))

    # Create dictionary that holds the attribute data accessible by field name
    # ie, {"permit_num":"2017-001", "work_type":"Minor", ...}
    fields = {}
    with arcpy.da.SearchCursor(permit_layer, permit_fields, where) as sc:
        for row in sc:
            # Change <Null> entries to be blank ("") instead of None
            row_blanked = [f if f else "" for f in row]
            fields = dict(zip(sc.fields, row_blanked))

    # Update text box variables.
    # Uses string substitution, so that {} gets replaced with whatever is in
    # the .format() after the closing quote mark ("). The dictionary allows us
    # to look up the value of a given field, so fields["permit_num"] give us
    # the string 2017-001.
    # This text goes directly into the textboxes' text parameter, so any
    # special formating recognized by ArcMap (like <BOL>) can be used

    # Simple one-liners
    parcel_no = "<BOL>{}</BOL>".format(fields["parcel"])
    permit_no = "<BOL>{}: {}</BOL>".format(fields["work_type"],
                                           fields["permit_num"])
    payment_type = "<BOL>Payment Type:</BOL> {}".format(
        fields["payment_type"])
    receipt = "<BOL>Receipt #:</BOL> {}".format(fields["receipt_number"])

    # If there's a deposit, show both Fee: and Deposit: ; if there's just a
    # fee, just show that. If neither deposit nor fee (like for a city), just
    # show $0.00
    if fields["deposit"]:
        fee = "<BOL>Deposit:</BOL> ${} <BOL>Fee:</BOL> ${}".format(
            fields["deposit"], fields["fee"])
    elif fields["fee"]:
        fee = "<BOL>Fee:</BOL> ${}".format(fields["fee"])
    else:
        fee = "<BOL>Fee:</BOL> $0.00"

    # If there's applicant/contact info, add that.
    if fields["applicant"] or fields["applicant_contact_no"]:
        lines = []  # list of each line, will be .join()'ed later to form text
        lines.append("<BOL>Contact Information:</BOL>")
        if fields["applicant"]:
            lines.append(fields["applicant"])
        lines.append("{}, {}".format(fields["applicant_contact_no"],
                                     fields["applicant_email"]))
        lines.append("{}, {}".format(fields["applicant_mailing_add"],
                                     fields["applicant_cty_st_zip"]))
        contact = "\r\n".join(lines)

    # If there's contractor info, add that.
    if fields["contractor"]:
        lines = []  # list of each line, will be .join()'ed later to form text
        lines.append("<BOL>Contractor Information:</BOL>")
        lines.append(fields["contractor"])
        lines.append("{}, {}".format(fields["contractor_contact_no"],
                                     fields["contractor_email"]))
        lines.append("{}, {}".format(fields["contractor_mailing_add"],
                                     fields["contractor_cty_st_zip"]))
        lines.append("License #: {}".format(fields["contractor_license"]))
        contractor = "\r\n".join(lines)

    # Add everything in the box under the map
    lines = []
    lines.append("<BOL>Project Type: </BOL>{}".format(
        fields["specific_work_type"]))
    lines.append("<BOL>Project Description: </BOL>{}".format(
        fields["project_description"]))
    lines.append("<BOL>Conditions:</BOL>")
    if fields["condition_1"]:
        lines.append(u"1. {}".format(fields["condition_1"]))
    if fields["condition_2"]:
        lines.append(u"2. {}".format(fields["condition_2"]))
    if fields["condition_3"]:
        lines.append(u"3. {}".format(fields["condition_3"]))
    if fields["condition_4"]:
        lines.append(u"4. {}".format(fields["condition_4"]))
    if fields["condition_5"]:
        lines.append(u"5. {}".format(fields["condition_5"]))
    if fields["condition_6"]:
        lines.append(u"6. {}".format(fields["condition_6"]))
    description = "\r\n".join(lines)

    # Public works inspector notes
    lines = []
    lines.append("<BOL>Road Findings from Public Works Inspector:</BOL>")
    lines.append("Total Width: {}, Paved Width: {}, Gravel Width: {}, Minimum Culvert Diameter: {}, Winter Maintenance: {}".format(
        fields["total_road_width"], fields["paved_width"],
        fields["gravel_width"], fields["culvert_diameter"],
        fields["winter_maintenance"]))
    inspector_findings = "\r\n".join(lines)

    # Set up map document
    mxd = arcpy.mapping.MapDocument(mxd_file)
    df = arcpy.mapping.ListDataFrames(mxd)[0]
    layers = arcpy.mapping.ListLayers(mxd)

    # Populate text boxes
    # Checks the text box's .name property to find the right text box. In ArcMap
    # layout view, set the location and size of the appropriate box and then set
    # it's Element Name (under Size and Position tab) to match these strings. The
    # box names match the variable names for simplicity's sake, but they don't have
    # to match.
    text_boxes = arcpy.mapping.ListLayoutElements(mxd, "TEXT_ELEMENT")
    for box in text_boxes:
        if box.name == "parcel_no":
            box.text = parcel_no
        elif box.name == "permit_no":
            box.text = permit_no
        elif box.name == "inspector_findings":
            box.text = inspector_findings
        elif box.name == "payment_type":
            box.text = payment_type
        elif box.name == "receipt":
            box.text = receipt
        elif box.name == "description":
            box.text = description
        elif box.name == "fee":
            box.text = fee
        # Set contact and contractor boxes and adjust position if one is empty
        elif box.name == "contractor":
            box.text = contractor
            # shift contractor box up half an inch if there's no contact info
            if contact == " ":
                box.elementPositionY += .5
        elif box.name == "contact":
            box.text = contact
            # shift contact box down half an inch if there's no contractor info
            if contractor == " ":
                box.elementPositionY -= .5

    # Set layers to be visible, get reference for permit layer to set extent
    for l in layers:
        l.visible = True
        if l.name == permit_layer:
            p_map_layer = l

    # Set definition query on permit layer
    p_map_layer.definitionQuery = where

    # Set extent
    df.extent = p_map_layer.getExtent()  # Set extent to match selected permit
    if df.scale < 10000:
        # If small scale (small feature, really zoomed in), set scale to 700%
        df.scale *= 7
    else:
        # If large scale (long or separated features), just add 1000 to scale
        df.scale += 1000

    # Clear any selections to avoid feature selection highlights in the map
    arcpy.SelectLayerByAttribute_management(p_map_layer, "CLEAR_SELECTION")

    # Create permit pdf
    out_path = os.path.join(arcpy.env.scratchFolder,
                            "Encroachment_Permit_{}.pdf".format(permit_number))
    arcpy.mapping.ExportToPDF(mxd, out_path)

    # Return pdf
    arcpy.SetParameter(4, out_path)

    del mxd

except arcpy.ExecuteError:
    # Log the errors as warnings on the server
    # (adding as errors would cause the task to fail)
    arcpy.AddWarning(arcpy.GetMessages(2))

    # Pass the exception message to the user
    messages.append("ERROR: ")
    messages.append(arcpy.GetMessages(2))

    # Use a bad link for the output pdf
    arcpy.SetParameter(4, "Error")

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
    messages.append("ERROR: ")
    messages.append(ve.args[0])

    # Use a bad link for the output pdf
    arcpy.SetParameter(4, "Please fix Parcel ID and run tool again")

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
    messages.append(e.args[0])

    # Use a bad link for the output pdf
    arcpy.SetParameter(4, "ERROR")

finally:
    output_string = "\n".join(messages)
    arcpy.SetParameterAsText(5, output_string)
