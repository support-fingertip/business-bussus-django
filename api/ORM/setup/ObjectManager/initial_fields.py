initial_fields = [
    {
        'name': 'name',
        'label': 'Name',
        'datatype': 'text',
        'length': 128,
        'unique': True,
        'required': True,
        'is_modifiable': True,
    },
    {
        'name': 'owner_id',
        'label': 'Owner',
        'length': 64,
        'datatype': 'lookup_relationship',
        'parent_object': 'users',
        "relationship_name": 'owner',
        'is_modifiable': False,
    },
    {
        'name': 'created_by_id',
        'label':'Created By',
        'length': 64,        
        'datatype': 'lookup_relationship',
        'parent_object': 'users',
        'relationship_name': 'created_by',
        'is_modifiable': False,
    },
    {
        'name': 'last_modified_by_id',
        'label': 'Last Modified By',
        'datatype': 'lookup_relationship',
        'parent_object': 'users',
        'relationship_name': 'last_modified_by',
        'is_modifiable': False,
    },
    {
        'name': 'last_modified_date',
        'label': 'Last Modified Date',
        'datatype': 'datetime',  
        'is_modifiable': False,
    },
    {
        'name': 'created_date',
        'label': 'Created Date',
        'datatype': 'datetime',  
        'is_modifiable': False,
    }
]