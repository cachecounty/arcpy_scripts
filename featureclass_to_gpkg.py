#*****************************************************************************
# 
#  Project:  Feature Class to Geopackage Script Tool
#  Purpose:  Copy feature class w/selected fields to a geopackage.
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

source_fc = arcpy.GetParameterAsText(0) # Feature Class
source_fields = arcpy.GetParameterAsText(1).split(';') # Multivalue; Field
gpkg_folder = arcpy.GetParameterAsText(2) # Folder
gpkg_name = arcpy.GetParameterAsText(3) # Optional; String
gpkg_fc_name = arcpy.GetParameterAsText(4) # Optional; String

try:
    # Create geopackage path
    # If the user has provided a name, attach extension if necessary
    if gpkg_name:
        if gpkg_name.endswith(".gpkg"):
            gpkg_fullname = gpkg_path
        else:
            gpkg_fullname = gpkg_name + ".gpkg"
     
    # Otherwise, defualt to the name of the input featureclass 
    else:
        fc_name = source_fc.split(os.sep)[-1]
        # Get rid of dbname.user.etc from SDE/db
        gpkg_name = fc_name.split(".")[-1] 
        gpkg_fullname = gpkg_name + ".gpkg"

    # Create full output path    
    gpkg_path = os.path.join(gpkg_folder, gpkg_fullname)    

    # Create GeoPackage
    if arcpy.Exists(gpkg_path):
        arcpy.AddWarning("Using existing Geopackage %s..." %gpkg_path)
    else:
        arcpy.AddMessage("Creating Geopackage %s..." %gpkg_path)
        arcpy.gp.CreateSQLiteDatabase(gpkg_path, "GEOPACKAGE")

    # Copy features from feature class into geopackage
    # Set up variables
    if not gpkg_fc_name:
        gpkg_fc_name = gpkg_name #"main." + gpkg_name
    gpkg_fc_path = os.path.join(gpkg_path, gpkg_fc_name)
    
    arcpy.AddMessage("Copying %s to %s..." %(source_fc, gpkg_fc_path))

    # Copy to in-memory feature class
    temp_fc = "in_memory\\temp_fc"
    if arcpy.Exists(temp_fc):
        arcpy.Delete_management(temp_fc)
    arcpy.CopyFeatures_management(source_fc, temp_fc)

    # Delete fields not desired in temp fc
    drop_fields = [f.name for f in arcpy.ListFields(temp_fc) if 
                                    f.name not in source_fields]
    # Don't delete OID, shape fields
    drop_fields.remove("objectid")
    drop_fields.remove("shape")
    arcpy.AddMessage(source_fields)
    arcpy.DeleteField_management(temp_fc, drop_fields)

    # CopyFeatures_management the temp fc to the geopackage
    arcpy.CopyFeatures_management(temp_fc, gpkg_fc_path)

except arcpy.ExecuteError:
    arcpy.AddError(arcpy.GetMessages(2))
    
except:
    tb = sys.exc_info()[2]
    tbinfo = traceback.format_tb(tb)[0]
    pymsg = "PYTHON ERRORS:\nTraceback info:\n" + tbinfo + "\nError Info:\n" + str(sys.exc_info()[1])
    arcpy.AddError(pymsg)
    arcpy.AddError("ARCPY ERRORS:\n%s\n" %arcpy.GetMessages(2))