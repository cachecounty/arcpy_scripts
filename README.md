# arcpy_scripts
Python Script Tools using ESRI's ArcPy library, including many that are exposed as Geoprocessing Services for use in webmaps.

Visit the Parcel and Zoning viewer at www.cachecounty.org/gis to see some of these tools in action.

# Runtime Requirements
All scripts require the arcpy library, installed as part of an ArcGIS Desktop installation. 
Some scripts rely on other third-party libraries available through pip. Check the import statements for each script.
These have all been written against Python 2.7, as used by ArcGIS 10.x, but many should have an eye to the future towards Python 3.x.

# Python Script Tools and Geoprocessing Services
Most of these scripts were created to serve as the backbone of Geoprocessing Services hosted on a local ArcGIS Enterprise server, but they should run just as well as stand-alone scripts. Some rely on existing .mxd files for arcpy.mapping outputs, but these mxds are not included in the repo. 

### encroachment_permit_generator.py
This script automatically generates an encroachment permit PDF based on a feature created via the Edit tool on an AGOL webmap. Using the geoprocessing widget, the user specifies the permit number. The script then grabs the appropriate data from the feature, updates text boxes in an MXD, and exports the MXD to a pdf. 

### featureclass_to_gpkg.py
Sharing data in open formats is important for transparency and wide-spread usability. This tool exports data from an SDE feature class to the OGC's geopackage specification, which is usable in most GIS software. This allows easy sharing of large, frequently updated feature classes (for example, parcel layers) without the limitations inherent in the old shapefile format.

### gis_summary.py
Another script exposed through the geoprocessing widget, this tool takes in a parcel ID and returns a PDF that identifies any geographic features on or near the parcel—wetlands, floodplains, natural hazard areas, zoning districts, city boundaries, etc. This allows planning staff to quickly and accurately identify any potential issues with a parcel at the beginning of the land use permit process. This improves customer service by speeding up the review process and eliminating the headache of dealing with new issues in the middle of the process because they weren't identified at the front end.

### mailing_list.py
State law often requires notice of land use actions to be sent to the owners of all properties within a certain distance of the subject property. This tool, again exposed via the geoprocessing widget, produces a CSV file of the parcel number, owner name, and owner address of these properties within a user-specified distance of the parcel.

### public_notice.py
Residents and citizens have a right and a responsibility to know what land use projects are happening in their cities and neighborhoods. However, the standard public noticing methods of posting an agenda in a public place or mailing notice to nearby property owners often obscurer this inherently spatial information behind textual addresses or parcel numbers. This tool automates the creation of features that can be exposed through a public webmap, allowing planning staff to quickly update a live map of current land use projects. It also automatically generates aerial maps, vicinity maps, and mailing lists for the convenience of planning staff. 
