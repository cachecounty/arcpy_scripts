#*****************************************************************************
#
#  Project:  Mailing List GP Service Script Tool
#  Purpose:  Creates a CSV of the mailing addresses of the owners of all
#            properties within a specified distance of the subject parcel based
#            on current records in the Assessor's table.
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
import traceback

# ======== Mailing list tool ========
# Creates a .csv containing the owner address info for all parcels within the
# specified buffer distance. Also creates scratch feature classes for the buffer
# and the selected parcels for display in a webmap. Buffer distance is specified
# in raw values to allow the script to check the distance. The unit is whatever
# projection the data/mxd use.

# ======== Setup ========
# Set up script tool in ArcMap: Set parameters as shown below.
# Stage service:
#   Run tool on mxd (which is registered in the server's data store) in arcmap.
#   Share results as geoprocessing service.
#   Use "Save A Service Definition" rather than publishing or overwriting.
#   Select "No Available Connection" and continue through the prompts.
#   In the service editor set the following parameters to Constant Value:
#       parcel_layer
#       tid_field
#       assessor_table
#       table_tid_field
#   After everything looks good, stage the service.
# Upload the staged service.
#   Toolbox -> Server Tools -> Publishing -> Upload Service Definition.
#   Choose the right service file, and use the "Override Service Properties"
#           to put it in the right folder (Folder type = EXISTING).
# Add to Web App Builder app:
#   Add a geoprocessing widget using ("consuming") the published service
#   Set the desired default values for the input parameters
#   Buffer and Neighboring_Parcels output parameters:
#       Set desired symbology for each
#       Disable the pop-up- the neighboring parcels don't have the newest info
#   Under Options, uncheck "Add result as opperational layer" to avoid
#           adding the temporary layers to the attribute table window
# And you're off to the races
# ======== ======== ========

TIDs = arcpy.GetParameterAsText(0) # Multivalue, "Any Value"
buffer_distance = arcpy.GetParameterAsText(1) # Raw value(Long), treated as feet
parcel_layer = arcpy.GetParameterAsText(2) # Table View
tid_field = arcpy.GetParameterAsText(3) # Field, derived from parcel_layer
assessor_table = arcpy.GetParameterAsText(4) # Table view (add table to mxd)
table_tid_field = arcpy.GetParameterAsText(5) # Field, derived from assessor_table
address_fields_raw = arcpy.GetParameterAsText(6) # Multivalue, Field, derived from assessor_table
# Paramter 7 is csv out path- file, derived output
# Parameter 8 is buffer feature class- Feature Layer, derived output
# Parameter 9 is neighboring parcels feature class- Feature Layer, derived output
try:
    arcpy.AddMessage(parcel_layer)

    # Set up variables
    # Split multivalue parameter on ";" to get list
    TID = TIDs.split(";")
    address_fields = address_fields_raw.split(";")

    # Limit to prevent selecting the entire county
    buffer_max = 1000

    # Table view name
    table_view = "assessor_table_view"

    # temp fc for surrounding parcels
    surrounding_parcels_fc = "in_memory\\surrounding_fc"

    # Path to buffer fc- feature class names can't have '-' in them
    buffer_fc = os.path.join(arcpy.env.scratchGDB, "buffer%s" %(TID[0]).replace('-', '_'))

    # Path to selected layer
    selected_fc = os.path.join(arcpy.env.scratchGDB, "selected%s" %(TID[0]).replace('-', '_'))

    # Clear any selections and in_memory objects for safety
    arcpy.SelectLayerByAttribute_management(parcel_layer, "CLEAR_SELECTION")
    arcpy.Delete_management("in_memory")

    # ========= Sanity Checks ===========
    # Make sure the distance won't be absurd
    if int(buffer_distance) > buffer_max:
        raise Exception("Buffer cannot be greater than %d feet" %(buffer_max))

    arcpy.AddMessage("Verifying input parcels...")

    # Regex pattern for parcel IDs
    pattern = "[0-9]{2}-[0-9]{3}-[0-9]{4}"

    # Make sure parcel numbers are valid
    for tid in TID:
        if tid and tid != "#":
            # Make sure the parcel ID is formatted correctly
            if not re.match(pattern, tid):
                raise Exception("Input Parcel IDs must be in the format " +
                                  "YY-YYY-YYYY, where Y is a single digit number." +
                                  " For example, 06-019-0009.")

            # Make sure parcel ID is a valid parcel
            where = tid_field + " = '" + tid + "'"
            with arcpy.da.SearchCursor(parcel_layer, tid_field, where) as search_cursor:
                if sum(1 for _ in search_cursor) < 1: #sums number of records
                    raise Exception("Cannot find parcel ID " + tid + " in parcel " +
                                      "list.")

    # ========= Select subject parcels ===========
    # Wrap parcel id's in single quotes for where clauses
    parcel_list = ["\'%s\'" %(p) for p in TID]

    # Set definition query for subject parcels
    if len(parcel_list) > 1:
        tid_string = ", ".join(parcel_list)
    elif len(parcel_list) == 1:
        tid_string = parcel_list[0]
    elif len(parcel_list) < 1:
        raise Exception("No parcels specified.")
    dq = tid_field + " IN (" + tid_string + ")"

    arcpy.AddMessage("Selecting parcels...")

    # Add all desired parcels to selection
    arcpy.SelectLayerByAttribute_management(parcel_layer, "ADD_TO_SELECTION", dq)

    # ========= Create feature classes for buffer and neighbor parcels ===========
    # Clear out buffer and selected fc's if they already exist
    if arcpy.Exists(buffer_fc):
        arcpy.Delete_management(buffer_fc)
    if arcpy.Exists(selected_fc):
        arcpy.Delete_management(selected_fc)

    # Create buffer to display for visual clarity
    arcpy.Buffer_analysis(parcel_layer, buffer_fc, buffer_distance,
                          dissolve_option = "ALL")
    arcpy.SetParameter(8, buffer_fc)

    # Select nearby features
    selection = arcpy.SelectLayerByLocation_management(parcel_layer,
                                                overlap_type = "WITHIN_A_DISTANCE",
                                                select_features = parcel_layer,
                                                search_distance = buffer_distance,
                                                selection_type = "NEW_SELECTION")

    # Make layer of selected features to display for visual clarity
    arcpy.CopyFeatures_management(parcel_layer, selected_fc)
    arcpy.SetParameter(9, selected_fc)

    # ========= Create table view of neighbor parcels from assessor ===========
    # Get nearby parcel IDs
    nearby_parcels = []
    with arcpy.da.SearchCursor(parcel_layer, tid_field) as parcel_cursor:
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
    arcpy.MakeTableView_management(assessor_table, table_view, table_where)

    # ========= Write out to csv ===========
    arcpy.AddMessage("Creating CSV...")

    # Create CSV of records from new feature class
    csv_file = os.path.join(arcpy.env.scratchFolder, "Addresses.csv")
    with open(csv_file, 'w') as csvfile:
        csvfile.write("sep=|\n")
        writer = csv.writer(csvfile, delimiter='|', lineterminator='\n')
        with arcpy.da.SearchCursor(table_view, field_names=address_fields) as cursor:
            writer.writerow(address_fields)
            for row in cursor:
                writer.writerow(row)

    # Sends path of the csv file back to the service handler
    arcpy.SetParameter(7, csv_file)

except Exception:
    e = sys.exc_info()
    tbinfo = traceback.format_tb(e[2])[0]
    err = "%s\n%s" %(tbinfo, e[1])
    arcpy.AddError(err)

# Make sure the in_memory data are removed no matter what happens
finally:
    # Be a good citizen and delete the in_memory workspace
    arcpy.Delete_management("in_memory")
