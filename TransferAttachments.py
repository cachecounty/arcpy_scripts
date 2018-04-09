import arcpy
import os
import csv
import datetime
import traceback
import sys
import mimetypes

def AddAttachments(att_table, match_table, match_field, match_name):
    '''
    Manually adds records to the attachment table based on a match table of
    rel_objectid's and the local paths to the saved attachments
    Created because arcpy.AddAttachments_management() doesn't like edit sessions

    att_table: The attachment table to which attachments will be added
    match_table: Table defining the new rel_oid and path to saved attachment
    match_field: The field containing the new rel_oid values
    match_name: The field containing the local path to the saved attachment
    '''

    # Initialize mimetypes if not already done:
    if not mimetypes.inited:
        mimetypes.init()

    match_entries = []
    with open(match_table, 'r') as table_file:
        reader = csv.reader(table_file, delimiter=',')
        for row in reader:
            match_entries.append(row)

    # Get indexes of fields
    match_field_index = match_entries[0].index(match_field)
    match_name_index = match_entries[0].index(match_name)

    # Strip header row
    data = match_entries[1:]

    fields = ["rel_objectid", "att_name", "data", "content_type", "data_size"]

    # Use match_name field (a path) to load the attachment as a memory view
    with arcpy.da.InsertCursor(att_table, fields) as icursor:
        for feature in data:
            with open(feature[match_name_index], 'rb') as f:

                # Read in attchment as a memory view
                att_mv = f.read()

                # Calculate the size of the file
                length = f.tell()

                # Determine file type from extension
                content_type = mimetypes.guess_type(feature[match_name_index])[0]

                att_name = feature[match_name_index].rpartition(os.path.sep)[2]

                row = (feature[match_field_index], att_name, att_mv,
                        content_type, length)
                icursor.insertRow(row)

def GetPaths(feature_class):
    '''
    Given a path to a feature class, will separate the gdb/sde, dataset (if
    applicable), and feature class names. If the feature class is not a member
    of a dateset, this name will be an empty string ('').

    Returns: 3-tuple: (Container path, dataset name, function class name)
    '''
    if ".gdb" in feature_class:
        container_index = feature_class.find(".gdb") + 4
    elif ".sde" in feature_class:
        container_index = feature_class.find(".sde") + 4
    else:
        raise ValueError("Feature class must be in a .sde or a .gdb")

    container_path = feature_class[:container_index]
    fc_name = feature_class.rpartition(os.path.sep)[2]

    # container_index + 1 skips the os.path.sep at the begining
    no_cont = feature_class[container_index + 1:]

    # If there's still an os.path.sep in the path, there's a datset; otherwise,
    # there isn't a dataset and the dataset variable is set to ''.
    if os.path.sep in no_cont:
        dataset = no_cont.rpartition(os.path.sep)[0]
    else:
        dataset = ''

    return (container_path, dataset, fc_name)

def GetAttachmentTablePath(feature_class):
    '''
    Given a feature class, will determine the appropriate path to a standard
    ESRI attachment table. Container must be a GDB or SDE.

    Assumes attachment table lives in root of GDB/SDE.

    Returns: Path to attachment table (string)
    '''

    paths = GetPaths(feature_class)
    table_name = paths[2] + "__ATTACH"
    table_path = os.path.join(paths[0], table_name)

    return table_path

# ==============================================================================
# This script copies attachments from origin_feature_class to dest_feature_class
# through the use of match values common to both feature classes.
#
# Pre-requisites:
# * Attachments must be enabled on the destination feature class
# * Both feature classes must have the match field, but the field name can be
#   different between them.
# * The match IDs must be unique in the origin_feature_class, a 1:1 relation
#   of match id:object id. If there are many origin object id's associated with
#   one match id, only the attachments of the last scanned object id will be
#   uploaded. If there are many destination object id's associated with one
#   match id (and one origin object id), the same attachments will be added to
#   each feature associated with that match id. If there are many origin and
#   destination object id's associated with a match id, the universe will
#   implode... probably...
# * The attachment tables must live in the root of the GDB/SDE, which I believe
#   is standard behavior for attachments.
# * The scratch folder must have enough space to hold all the attachments.
# * The destination feature class must reside in a file GDB or an SDE GDB.
#
# The script is designed to be used as a script tool via arcmap/catalog, but
# could be modified to run stand-alone.
#
# Any attachments to features corresponding to a <null> match id value will be
# downloaded from the origin feature class but will not be attached to the
# destination feature class as there is no valid match id:object id mapping.
#
# Basic logic:
#   1. Create origin match id dictionary
#   2. Loop through origin object ids and download associated attachments.
#   3. Create dictionary matching downloaded paths to origin object ids.
#   4. Create destination match id dictionary.
#   5. Translate origin OIDs to destination OIDs and create new dictionary
#       matching downloaded paths to destination OIDs.
#   6. Use new attachment dictionary to upload attachments to destination.
#
# ==============================================================================
# Variables
# Could be paramaterized
origin_feature_class = arcpy.GetParameterAsText(0)
dest_feature_class = arcpy.GetParameterAsText(1)
ofc_match_field = arcpy.GetParameterAsText(2)
dfc_match_field = arcpy.GetParameterAsText(3)
scratch_folder_base = arcpy.GetParameterAsText(4)
uname = arcpy.GetParameterAsText(5)
pw = arcpy.GetParameterAsText(6)

# Should probably be constant, assuming a bog-standard attachment setup
start = datetime.datetime.now()
scratch_folder = os.path.join(scratch_folder_base, start.strftime("%Y%m%d_%H%M%S"))
fc_key_field = 'OBJECTID'

table_key_field = "REL_OBJECTID"
att_name_field = "ATT_NAME"
att_data_field = "DATA"
add_table_path = os.path.join(scratch_folder, "add_table.csv")

# Field names in match tables
match_field = "ID"
match_name = "NAME"

# Field names in attachment table
table_fields = [table_key_field, att_name_field, att_data_field]

# Create attachment table paths from feature class path
origin_att_table = GetAttachmentTablePath(origin_feature_class)
dest_att_table = GetAttachmentTablePath(dest_feature_class)

# Internal Collections
# List of primary keys in the origin_fc, used to download attachments
fc_keys = []
# Dictionary of paths to attachments downloaded from origin
# {origin OID:[path1, path2, ...]}
orig_atts = {}
# Dictionary of paths to downloaded attachments to be added to destination
# {dest OID:[new_path1, new_path2, ...]}
dest_atts = {}
# Dictionary of origin OIDs to Match IDs
# {Match ID:origin OID}
origin_match_dict = {}
# Dictionary of destination OIDs to Match IDs. Match ID field name can be
# different between the fc's, but we care about the values, not the field name.
# {Match ID:dest OID}
dest_match_dict = {}

# Set up workspace
workspace = GetPaths(dest_feature_class)[0]
arcpy.env.workspace = os.path.dirname(workspace)

is_gdb = ".gdb" in dest_feature_class
is_versioned_sde = ".sde" in dest_feature_class and arcpy.Describe(dest_feature_class).isVersioned

try:
    # ==========================================================================
    # Sanity Checks
    if not arcpy.Exists(origin_feature_class):
        raise IOError("Invalid origin feature class path: " + origin_feature_class)
    if not arcpy.Exists(origin_att_table):
        raise IOError("Origin attachment table not found: " + origin_att_table)

    if not arcpy.Exists(dest_feature_class):
        raise IOError("Invalid new feature class path: " + dest_feature_class)
    if not arcpy.Exists(dest_att_table):
        raise IOError("New attachment table not found: " + dest_att_table)

    # Different db backends (PostgreSQL, SQL Server, etc) use upper or lower
    # case field names. The SDE engine aparently handles this seamlessley when
    # doing operations, but our sanity checks need to check lower case as well.
    old_fc_fields = [f.name for f in arcpy.ListFields(origin_feature_class)]
    if ofc_match_field not in old_fc_fields:
        if ofc_match_field.lower() not in old_fc_fields:
            raise ValueError("Match field not in original feature class: " + ofc_match_field)
    new_fc_fields = [f.name for f in arcpy.ListFields(dest_feature_class)]
    if dfc_match_field not in new_fc_fields:
        if dfc_match_field.lower() not in new_fc_fields:
            raise ValueError("Match field not in new feature class: " + dfc_match_field)
    # ==========================================================================

    # Create scratch folder if it doesn't already exist
    os.makedirs(scratch_folder)

    # Get the original primary key (OID) and Match ID for every feature from
    # origin feature class
    # Creates list of keys (fc_keys) and a dictionary {Match ID:OID}
    arcpy.AddMessage("Getting original OIDs...")
    with arcpy.da.SearchCursor(origin_feature_class, ['OID@', ofc_match_field]) as scursor:
        for feature in scursor:
            fc_keys.append(feature[0])
            origin_match_dict[feature[1]] = feature[0]

    # Get the attachment key and image name for each attachment, and save image
    # to the scratch folder so that we can upload it to the dest att table
    arcpy.AddMessage("Getting existing attachments...")
    with arcpy.da.SearchCursor(origin_att_table, table_fields) as tcursor:
        for feature in tcursor:
            if feature[0] in fc_keys: # feature[0] is origin_OID

                # Write images out to disk.
                # Creates a subfolder for each origin OID.
                subfolder = os.path.join(scratch_folder, str(feature[0]))
                if not os.path.exists(subfolder):
                    os.makedirs(subfolder)
                att_path = os.path.join(subfolder, feature[1])
                photo = feature[2]
                with open (att_path, 'wb') as att_file:
                    att_file.write(photo.tobytes())
                # If the origin OID is not in the dictionary yet, add it.
                # Then, we append the att_path to the list associated with the
                # origin OID
                if feature[0] not in orig_atts:
                    # Create empty list associated with that dictionary key
                    orig_atts[feature[0]] = []
                # Appends path to list
                # {Origin_OID, [path1, path2, ...]}
                orig_atts[feature[0]].append(att_path)

    # Create destination Match ID:new OID using origin Match ID as test.
    # Loop through destination feature class with search cursor. If the Match ID for the
    # origin feature is a key in origin_match_dict, create an entry in dest_match_dict
    # using the Match ID and the OID from the new feature class.
    # Will only get match IDs that are also in the origin match dictionary. If (?)
    #
    with arcpy.da.SearchCursor(dest_feature_class, ['OID@', dfc_match_field]) as scursor:
        for f in scursor:
            if f[1] in origin_match_dict:
                dest_match_dict[f[1]] = f[0]

    # Collections:
    # attachments: {origin OID:[path1, path2, ...]}
    # origin_match_dict: {Match ID:origin OID}
    # dest_match_dict: {Match ID:dest OID}

    # Now translate orig_atts {orig OID:[paths]} to dest_atts {dest OID:[paths]}
    # by looping through match ID:origin_oid pairs
    for match_id, origin_oid in origin_match_dict.iteritems():
        # If the origin oid is a key in the attachments dictionary (if there are 
        # attachments for that OID)
        if origin_oid in orig_atts:
            # Create new entry in the dest_atts dictionary using the new OID and
            # the paths from the old attachments dictionary via the match_id
            new_oid_key = dest_match_dict[match_id]
            dest_atts[new_oid_key] = orig_atts[origin_oid]

    # Now we have dest_atts: {dest OID:[path1, path2, ...]}

    # Write out an add match table using dest_atts
    with open(add_table_path, 'wb') as file:
        writer = csv.writer(file, delimiter=',')

        # Header Row
        writer.writerow([match_field, match_name])

        # Records
        for key in dest_atts:
            for value in dest_atts[key]:
                writer.writerow([str(key), value])
        del writer


    # Split here: if file gdb, we just use a simple edit session. If versioned
    # SDE, do versioning method.

    if is_gdb:
        # Manually handling edit session instead of using a "with...as" because it
        # gives us "NULL result without error in PyObject_Call" or "Insufficient
        # Permission" errors on the with...as or the DeleteAttachments() lines,
        # respectively.
        arcpy.AddMessage("Opening edit session in a file GDB...")
        edit = arcpy.da.Editor(workspace)
        edit.startEditing()
        edit.startOperation()

        # Custom functions as the arcpy equivalents don't handle edit sessions
        # very well. Just direct edits to the attach table based on the match
        # tables created as per normal.
        arcpy.AddMessage("Adding attachments to new feature class...")
        AddAttachments(dest_att_table, add_table_path, match_field, match_name)

        arcpy.AddMessage("Closing edit session...")
        edit.stopOperation()
        edit.stopEditing(True)
        #arcpy.AddMessage(arcpy.GetMessages())

    # Versioned method
    elif is_versioned_sde:

        # Version variables
        v_name = "UPDATES"
        v_parent = "sde.DEFAULT"

        # Variables for new db connection file
        out_folder = scratch_folder
        out_name = "updates.sde"
        db_platform = "POSTGRESQL"
        instance = "archangel, 5433"
        auth = "DATABASE_AUTH"
        save = "SAVE_USERNAME"
        db = "giscache"
        schema = "#"
        v_type = "TRANSACTIONAL"
        version = ".".join((uname, v_name))

        # Determine the sde.DEFAULT workspace
        sde_path = GetPaths(dest_att_table)[0]

        # Path to our temporary version's connection file. Also used as the edit
        # workspace.
        connection = os.path.join(out_folder, out_name)

        # Set up workspace? Necessary???
        arcpy.env.workspace = os.path.dirname(connection)

        # Make sure we've been given a username and password
        if not uname or not pw:
            raise arcpy.ExecuteError("A username and password for the " +
                                        "versioned SDE must be provided.")

        # Raise error if updates version already exists
        for existing in arcpy.ListVersions(sde_path):
            if version in existing:
                raise arcpy.ExecuteError("Version " + version + " already in use." +
                                            " Please specify a different version.")

        # Create a new temporary version that will be edited, then reconciled and
        # posted back to sde.DEFAULT.
        arcpy.AddMessage("Creating new version for updating...")
        arcpy.CreateVersion_management(sde_path, v_parent, v_name, "PROTECTED")

        # Sanity checks on version connection files
        if os.path.exists(connection):
            raise IOError("Connection file " + connection + " already exists." +
                            " Remove or rename existing file.")
        if not os.path.exists(out_folder):
            raise IOError("Connection file output folder " + out_folder +
                            " does not exist.")

        # Create a new connection file for the temporary version that will be used
        # to edit the feature class.
        arcpy.CreateDatabaseConnection_management(out_folder, out_name, db_platform,
                                                    instance, auth, uname, pw, save,
                                                    db, schema, v_type, version)

        # Update the path to the new attachment table to point to the new
        # temporary SDE version
        parts = GetPaths(dest_att_table)
        # If it's in a dataset, we create a path using the dataset (parts[1])
        if parts[1]:
            dest_att_table_v = os.path.join(connection, parts[1], parts[2])
        # Otherwise, it's just the SDE and the feature class.
        else:
            dest_att_table_v = os.path.join(connection, parts[2])

        arcpy.AddMessage("Opening edit session in a versioned SDE...")
        edit = arcpy.da.Editor(connection)
        edit.startEditing()
        edit.startOperation()

        arcpy.AddMessage("Adding attachments to new feature class...")
        AddAttachments(dest_att_table_v, add_table_path, match_field, match_name)

        arcpy.AddMessage("Closing edit session...")
        edit.stopOperation()
        edit.stopEditing(True)


        # Reconcile and post changes to sde.DEFAULT, delete temporary version
        in_db = sde_path
        mode = "ALL_VERSIONS"
        target_version = v_parent
        edit_version = version
        locks = "LOCK_ACQUIRED"
        abort = "NO_ABORT"
        conflicts = "BY_ATTRIBUTE"
        conflict_res = "FAVOR_EDIT_VERSION"
        post = "POST"
        delete = "DELETE_VERSION"
        arcpy.ReconcileVersions_management(in_db, mode, target_version,
                                            edit_version, locks, abort,
                                            conflicts, conflict_res, post,
                                            delete)

        # Delete temporary version SDE connection file
        if os.path.exists(connection):
            os.remove(connection)

    else:
        raise ValueError("New attachment table must be in a file GDB or a versioned SDE: " + dest_att_table)

    arcpy.AddMessage(arcpy.GetMessages())

except arcpy.ExecuteError:
    arcpy.AddError(arcpy.GetMessages(2))

except Exception as err:
    # Get the traceback object
    tb = sys.exc_info()[2]
    tbinfo = traceback.format_tb(tb)[0]

    # Concatenate information together concerning the error into a message string
    pymsg = "PYTHON ERRORS:\nTraceback info:\n" + tbinfo + "\nError Info:\n" + str(sys.exc_info()[1])
    msgs = "\nArcPy ERRORS:\n" + arcpy.GetMessages(2) + "\n"

    # Return python error messages for use in script tool or Python Window
    arcpy.AddError(pymsg)
    arcpy.AddError(msgs)

    # Print Python error messages for use in Python / Python Window
    print(pymsg)
    print(msgs)

finally:
    # If the temporary version or connection file were created, we need to
    # delete them
    if is_versioned_sde:
        # Stop editing
        if 'edit' in globals() and edit.isEditing:
            edit.abortOperation()
            edit.stopEditing(False)
            arcpy.AddMessage("Stopped edit session")
        # Delete temporary version from SDE
        for existing in arcpy.ListVersions(sde_path):
            if version in existing:
                arcpy.DeleteVersion_management(sde_path, version)
                arcpy.AddMessage("Deleted temporary SDE version: " + version)
        # Delete temporary version connection file
        if os.path.exists(connection):
            os.remove(connection)
            arcpy.AddMessage("Deleted connection file: " + connection)





