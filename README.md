# arcpy_scripts
Python Script Tools using ESRI's ArcPy library, including many that are exposed as Geoprocessing Services for use in webmaps.

Visit the Parcel and Zoning viewer at www.cachecounty.org/gis to see some of these tools in action.

# Runtime Requirements
All scripts require the arcpy library, installed as part of an ArcGIS Desktop installation. 
Some scripts rely on other third-party libraries available through pip. Check the import statements for each script.
These have all been written against Python 2.7, as used by ArcGIS 10.x, but many should have an eye to the future towards Python 3.x.

# Python Script Tools and Geoprocessing Services
Many of these scripts were created to serve as the backbone of Geoprocessing Services hosted on a local ArcGIS Enterprise server, but they should run just as well as stand-alone scripts. Some rely on existing .mxd files for arcpy.mapping outputs, but these mxds are not included in the repo. 

Other scripts are small one-off projects or prototyping scripts for figuring out different functionality. These may not run all that well right out of the box.
