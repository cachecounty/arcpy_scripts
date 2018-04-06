#*****************************************************************************
# 
#  Project:  Major Land Use Project Feature Creation GP Script Tool
#  Purpose:  Interface for planning staff to create major land use project
#            features and automatically generate aerial map, vicinity map, and
#            mailing list.
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
import re
import os
import csv
import sys
import traceback

TIDs = arcpy.GetParameterAsText(0) # Multivalue paramter
project_type = arcpy.GetParameterAsText(1) # Specify values in script tool
project_name = arcpy.GetParameterAsText(2)
project_address = arcpy.GetParameterAsText(3)
request_summary = arcpy.GetParameterAsText(4)
meeting_date = arcpy.GetParameterAsText(5)
sr_link = arcpy.GetParameterAsText(6)
status = arcpy.GetParameterAsText(7) # Again, specify values
buffer_distance = arcpy.GetParameterAsText(8)
parcel_layer = arcpy.GetParameterAsText(9) # Layer of the mxd
projects_layer = arcpy.GetParameterAsText(10) # Layer of the mxd
# Parameters 11-13 used as output parameters below
mxd_file = arcpy.GetParameterAsText(14)
lua = arcpy.GetParameterAsText(15) # Again, specify values
solo_table = arcpy.GetParameterAsText(16) # Table in mxd
# Parameter 17 used as message/error parameter below


# Previous notes below left here for posterity's sake
# ---------------------------------------------------
# Set up paths to connection file for feature classes
# SDE connection file is placed in "path" folder that is in the same directory
# as the script. When shared as a GP service, "path" and the connection file
# will be uploaded to the server. the GP service will then use the connection
# file to access the SDE.
# script_dir = sys.path[0]
# folder = os.path.join(script_dir, "path")
# parcel_fc = os.path.join(folder, "path/to/fc")
# project_fc = os.path.join(folder, path/to/fc")

# Using references to the layers instead of direct links to the SDE presents the following problems:
# 1. If mapping stuff is commented out, geoprocessing fails to stage with a consolidating data error.
# 2. If mxd is refferred to using "CURRENT": error, broken link and not in data store
# 3. If mxd is reffered to using direct UNC path, it's not on the data store
# 4. If mxd is referred to using parameter, it's not in the data store.
# Can't verify, but my guess is that even if I could get the mxd stuff figured out, the layers would still bomb out at staging (#1)
# ------------------------------------------------------

# Set up variables
# MultiValue parameters come in as a single long string with each entry
# separated by a ";". split(";") creates a list by spliting on the ";"
TID = TIDs.split(";")
temp_fc = "in_memory\\temp_fc"
surrounding_parcels_fc = "in_memory\\surrounding_fc"
table_view = "assessor_table_view"
parcel_tid_field = "tax_id"
table_tid_field = "parcel_number"
address_fields_list = ["parcel_number", "owner_name", "owner_address1", "owner_city_state_zip"]
fields = {
            "projecttype" : "TEXT",
            "projectname" : "TEXT",
            "projectaddress" : "TEXT",
            "projectsummary" : "TEXT",
            "nextmeeting" : "DATE",
            "staffreport" : "TEXT",
            "status" : "TEXT",
            "parcelids" : "TEXT",
            "active" : "TEXT",
            "landuseauthority" : "TEXT"
          }

field_list = ["projecttype", "projectname", "projectaddress",
              "projectsummary", "nextmeeting", "staffreport", "status", "parcelids",
              "active", "landuseauthority"]

verified_parcels = []

messages = []

try:
    arcpy.AddMessage("Creating LU Project Polygon...")
    messages.append("Creating LU Project Polygon...")

    # Clear any selections and in_memory objects for safety
    arcpy.SelectLayerByAttribute_management(parcel_layer, "CLEAR_SELECTION")
    arcpy.Delete_management("in_memory")

    # Regex pattern for parcel IDs
    pattern = "[0-9]{2}-[0-9]{3}-[0-9]{4}"

    # Make sure parcel numbers are valid
    for tid in TID:
        if tid and tid != "#":
            # Make sure the parcel ID is formatted correctly
            if not re.match(pattern, tid):
                raise ValueError("Input Parcel IDs must be in the format " +
                                  "YY-YYY-YYYY, where Y is a single digit number." +
                                  " For example, 06-019-0009.")

            # Make sure parcel ID is a valid parcel
            where = parcel_tid_field + " = '" + tid + "'"
            with arcpy.da.SearchCursor(parcel_layer, parcel_tid_field, where) as search_cursor:
                if sum(1 for _ in search_cursor) < 1: #sums number of records
                    raise ValueError("Cannot find parcel ID " + tid + " in parcel " +
                                      "list.")

    # Check for any characters in the project name that would cause havok with the file system
    file_pattern = r'[<>:"/\|?*]+'
    if re.search(file_pattern, project_name):
        raise ValueError("Please enter a different project name that does not contain the following characters: <>:\"/\\|?*")

    # Wrap parcel id's in single quotes for where clauses
    parcel_list = ["\'%s\'" %(p) for p in TID]

    # Set definition query
    if len(parcel_list) > 1:
        tid_string = ", ".join(parcel_list)
    elif len(parcel_list) == 1:
        tid_string = parcel_list[0]
    elif len(parcel_list) < 1:
        raise ValueError("No parcels specified.")
    dq = parcel_tid_field + " IN (" + tid_string + ")"

    # Add all desired parcels to selection
    arcpy.SelectLayerByAttribute_management(parcel_layer, "ADD_TO_SELECTION", dq)

    # Dissolve parcels (if needed) into temporary feature class
    arcpy.Dissolve_management(parcel_layer, temp_fc)

    # Add fields to temporary feature class
    for field, ftype in fields.iteritems():
        if ftype is "TEXT":
            arcpy.AddField_management(temp_fc, field, ftype, field_length=400)
        else:
            arcpy.AddField_management(temp_fc, field, ftype)

    # Update fields with info from parameters to temporary feature class
    with arcpy.da.UpdateCursor(temp_fc, field_list) as update_cursor:
        for row in update_cursor:
            row[0] = project_type
            row[1] = project_name
            row[2] = project_address
            row[3] = request_summary
            row[4] = meeting_date
            row[5] = sr_link
            row[6] = status
            row[7] = ", ".join(TID)
            row[8] = "Yes"
            row[9] = lua
            update_cursor.updateRow(row)

    # Append merged parcel to Project FC
    arcpy.Append_management(temp_fc, projects_layer, "NO_TEST")

    arcpy.AddMessage("Creating mailing list...")
    messages.append("Creating mailing list...")

    # ============= Create public notice mailing lists =============
    # Select nearby features (assumes parcel_layer selection is still valid)
    selection = arcpy.SelectLayerByLocation_management(parcel_layer, overlap_type = "WITHIN_A_DISTANCE",
                                                select_features = parcel_layer,
                                                search_distance = buffer_distance,
                                                selection_type = "NEW_SELECTION")

    # Get nearby parcel IDs
    nearby_parcels = []
    with arcpy.da.SearchCursor(parcel_layer, parcel_tid_field) as parcel_cursor:
        nearby_parcels = ["\'%s\'" %(r[0]) for r in parcel_cursor]

    # Table definition query
    if len(nearby_parcels) > 1:
        table_tid_string = ", ".join(nearby_parcels)
    elif len(nearby_parcels) == 1:
        table_tid_string = nearby_parcels[0]
    else:
        table_tid_string = ""
    table_where = "%s IN (%s)" %(table_tid_field, table_tid_string)

    # Make table view with subsetted entries
    arcpy.MakeTableView_management(solo_table, table_view, table_where)

    # ========= Write out to csv ===========
    arcpy.AddMessage("Creating CSV...")
    messages.append("Creating CSV...")

    # Create CSV of records from new feature class
    csv_file = os.path.join(arcpy.env.scratchFolder, "Addresses.csv")
    with open(csv_file, 'w') as csvfile:
        csvfile.write("sep=|\n")
        writer = csv.writer(csvfile, delimiter='|', lineterminator='\n')
        with arcpy.da.SearchCursor(table_view, field_names=address_fields_list) as cursor:
            writer.writerow(address_fields_list)
            for row in cursor:
                writer.writerow(row)

    # Sends path of the csv file back to the service handler
    arcpy.SetParameter(11, csv_file)

    arcpy.AddMessage("Setting up mxd for mapping...")
    messages.append("Setting up mxd for mapping...")
    # ============= Create Overview and Aerial maps for staff Report =============
    # Clear selection to avoid selection symbology in exported maps
    arcpy.SelectLayerByAttribute_management(parcel_layer, "CLEAR_SELECTION")

    # Get the map document, data frame, and layers
    arcpy.AddMessage("MXD Path: " + mxd_file)
    mxd = arcpy.mapping.MapDocument(mxd_file)
    df = arcpy.mapping.ListDataFrames(mxd)[0]
    layers = arcpy.mapping.ListLayers(mxd)
    for l in layers:
        if l.name == "Aerial Parcels":
            a_layer = l
        elif l.name == "Vicinity Parcels":
            v_layer = l
        elif l.name == "Imagery":
            i_layer = l

    # Uses definition query created earlier
    a_layer.definitionQuery = dq
    v_layer.definitionQuery = dq

    arcpy.AddMessage("Creating vicinity map...")
    messages.append("Creating vicinity map...")
    # Vicinity Map: turn on vicinity parcels, turn off imagery, zoom to layer, add 10k to extent, export to jpg @ 600dpi
    v_layer.visible = True
    a_layer.visible = True
    i_layer.visible = False
    df.extent = v_layer.getExtent() # Set extent to match layers
    df.scale = df.scale + 10000 # Add 10k to scale to give us the vicinity view
    out_path_v = os.path.join(arcpy.env.scratchFolder, project_name + " Vicinity.jpg")
    arcpy.mapping.ExportToJPEG(mxd, out_path_v, resolution=600)
    arcpy.SetParameter(12, out_path_v)

    arcpy.AddMessage("Creating aerial map...")
    messages.append("Creating aerial map...")
    # Aerial Map: turn off vicinity parcels, turn on imagery, zoom to layer, export
    v_layer.visible = False
    a_layer.visible = True
    i_layer.visible = True
    df.extent = v_layer.getExtent() # Set extent to match layers
    df.scale += 200 # Add 200 to scale to give a little bit of space at the edges

    # # Use Logan's image service for imagery...
    # server_url = "http://gis.loganutah.org/arcgis/services/Ortho/Ortho2016_Cache/ImageServer"
    # layer_name = "in_memory\\imagery_layer"
    #
    # # Calculate new extent for imagery
    # # New extent is delta_x map units wider, where delta_x = map distance * new scale - original width
    # # To center new extent, add/subtract by delta_x by 2 (and similar for delta_y and height)
    # x_md = df.elementWidth / mxd.pageSize.width # Map distance in feet is df width / mxd width (both in inches)
    # y_md = df.elementHeight / mxd.pageSize.height
    # delta_x = x_md * df.scale - a_layer.getExtent().width
    # delta_y = y_md * df.scale - a_layer.getExtent().height
    #
    # xmin = a_layer.getExtent().XMin - (delta_x / 2.0)
    # xmax = a_layer.getExtent().XMax + (delta_x / 2.0)
    # ymin = a_layer.getExtent().YMin - (delta_y / 2.0)
    # ymax = a_layer.getExtent().YMax + (delta_y / 2.0)
    # ex = arcpy.Extent(xmin, ymin, xmax, ymax)
    #
    # arcpy.MakeImageServerLayer_management(server_url, layer_name, ex)
    # image_layer = arcpy.mapping.Layer(layer_name)
    # arcpy.mapping.InsertLayer(df, i_layer, image_layer)
    # image_layer.visible = True

    out_path_a = os.path.join(arcpy.env.scratchFolder, project_name + " Aerial.jpg")
    arcpy.mapping.ExportToJPEG(mxd, out_path_a, resolution=600)
    arcpy.SetParameter(13, out_path_a)

    del mxd

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
    messages.append(" --- ERROR: ")
    messages.append(ve.args[0])

except Exception as ex:
    # Get the traceback object
    tb = sys.exc_info()[2]
    tbinfo = traceback.format_tb(tb)[0]

    # Concatenate information together concerning the error into a message string
    pymsg = "PYTHON ERRORS:\nTraceback info:\n" + tbinfo + "\nError Info:\n" + str(sys.exc_info()[1])
    msgs = "\nArcPy ERRORS:\n" + arcpy.GetMessages(2) + "\n"

    # Log the errors as warnings on the server (adding as errors would cause the task to fail)
    arcpy.AddWarning(pymsg)
    arcpy.AddWarning(msgs)

    messages.append(ex.args[0])

    # Sometimes the database state changes while adding the polygon (someone
    # saves edits, etc). The GP service doesn't handle that all that well
    # (without going through the hassle of an edit session). This manifests as
    # the script failing once, and then future attempts seem to succeed but
    # don't add polygons. The solution is to restart the service and add them
    # again.
    if "version has been redefined" in ex.args[0]:
        messages.append("\n")
        messages.append(" --- Error adding project polygon. Please ask GIS to restart the Geoprocessing Service before trying again. --- ")
        messages.append("\n")

    # Sometimes the call to add the imagery from Logan City times out. The
    # polygons get created, but the map fails. The solution is to run the tool
    # again to add tempory projects that have the same boundaries, thus
    # creating the maps, and then delete the temporary projects.
    elif "Failed to get raster" in ex.args[0]:
        messages.append(" --- Error creating aerial overview map. Please create a new, temporary polygon to recreate the maps and mailing list, and then delete the temporary polygon. --- ")

finally:
    output_string = "\n".join(messages)
    arcpy.SetParameterAsText(17, output_string)

    # Be a good citizen and delete the in_memory workspace
    arcpy.Delete_management("in_memory")
