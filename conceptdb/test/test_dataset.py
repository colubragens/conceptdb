import conceptdb
from conceptdb.metadata import Dataset

conceptdb.connect_to_mongodb('test')

def test_dataset():
    dataset = Dataset.make(language='en', name='/data/test')
    
    # Make sure it was saved to the database
    assert dataset.id is not None

    # Make sure its attributes are readable
    dataset.language
    dataset.name

    #test methods
    dataset.nl()

    dataset.check_consistency()

    # Clean up by dropping the Dataset collection
    Dataset.drop_collection()

