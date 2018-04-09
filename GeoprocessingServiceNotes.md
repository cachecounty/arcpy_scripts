# Creating a Geoprocessing Service From a Script Tool

ESRI has some pretty good documentation on this already; this is meant to be a simple summary explaining how our script tools get turned into geoprocessing widgets in our webmaps.

1. Setup script as a python-based Script Tool in ArcMap
    1. Set the source to point to the script
    2. Set the parameters as specified in the script
2. Run the Script Tool in ArcMap
3. Share the (successful) results of the Script Tool with Share As -> Geoprocessing Service
    1. Publish or Overwrite a service (see note below for our workaround)
    2. Select a connection, folder, and service name
    3. Configure the options in the Service Editor according to the Script Tool's requirements; pay attention to input mode for each parameter
4. Note the URL of your new Geoprocessing Service, or share it via AGOL
5. In the AGOL Web AppBuilder, add a new Geoprocessing Widget
    1. Enter the URL of the GP Service, or select 'ArcGIS Online' and find your shared service.
    2. Verify the parameters came across correctly and set their default values.
    3. Change the icon, if desired.

### Our Workaround for Publishing Geoprocessing Services
For some reason, our particular setup causes the Share As -> Geoprocessing Service step to fail when we try to publish directly to a service or overwrite an existing service. To get around this, we choose "Save a service definition file" and then "No available connection." After setting everything up in the Service Editor, we manually upload the service definition via Server Tools -> Publishing -> Upload Service Definition in the Toolbox.

To update an existing GP Service, we first have to delete the existing service before uploading our new service definition.
