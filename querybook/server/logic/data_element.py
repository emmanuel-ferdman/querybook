from typing import Union

from app.db import with_session
from const.data_element import (
    DataElementAssociationDict,
    DataElementAssociationProperty,
    DataElementAssociationTuple,
    DataElementAssociationType,
    DataElementTuple,
)
from lib.logger import get_logger
from logic.user import get_user_by_name
from models.data_element import DataElement, DataElementAssociation
from sqlalchemy.sql.expression import case

LOG = get_logger(__file__)


@with_session
def get_data_element_by_id(id: int, session=None):
    return DataElement.get(id=id, session=session)


@with_session
def get_data_element_by_name(name: str, session=None):
    return DataElement.get(name=name, session=session)


@with_session
def check_query_metastore_has_data_elements(metastore_id, session=None):
    has_data_elements = (
        session.query(DataElement).filter_by(metastore_id=metastore_id).first()
    )
    return has_data_elements is not None


@with_session
def search_data_elements_by_keyword(keyword: str, limit=20, session=None):
    return (
        session.query(DataElement)
        .filter(DataElement.name.like("%" + keyword + "%"))
        .order_by(
            case([(DataElement.name.startswith(keyword), 0)], else_=1),
            DataElement.name.asc(),
        )
        .limit(limit)
        .all()
    )


@with_session
def get_data_element_association_by_column_id(
    column_id: int, session=None
) -> DataElementAssociationDict:
    associations = (
        session.query(DataElementAssociation)
        .filter(DataElementAssociation.column_id == column_id)
        .all()
    )
    if not associations:
        return None

    # check if there are more than 1 association type
    association_types = set([r.type for r in associations])
    if len(association_types) > 1:
        LOG.error(
            f"Column {column_id} has more than one data element associated with it"
        )
        return None

    data_element = {}
    for row in associations:
        data_element["type"] = row.type.value
        data_element[row.property_name] = (
            row.data_element if row.data_element else row.primitive_type
        )
    return data_element


@with_session
def get_column_to_data_element_mapping(
    column_ids: list[int], session=None
) -> dict[int, DataElementAssociationDict]:
    """Get all data element associations for multiple columns at once, organized by column_id

    It retrieves associations for multiple columns in a single query.
    """
    if not column_ids:
        return {}

    # Get all associations in a single query
    associations = (
        session.query(DataElementAssociation)
        .filter(DataElementAssociation.column_id.in_(column_ids))
        .all()
    )

    # Group associations by column_id
    grouped_associations = {}
    for association in associations:
        if association.column_id not in grouped_associations:
            grouped_associations[association.column_id] = []
        grouped_associations[association.column_id].append(association)

    # Process each column's associations into the expected format
    result = {}
    for column_id, column_associations in grouped_associations.items():
        # Check for multiple association types (error case)
        association_types = set([r.type for r in column_associations])
        if len(association_types) > 1:
            LOG.error(
                f"Column {column_id} has more than one data element associated with it"
            )
            continue

        # Create the data element dictionary for this column
        data_element = {}
        for row in column_associations:
            data_element["type"] = row.type.value
            data_element[row.property_name] = (
                row.data_element if row.data_element else row.primitive_type
            )

        result[column_id] = data_element

    return result


@with_session
def create_or_update_data_element(
    metastore_id: int, data_element_tuple: DataElementTuple, commit=True, session=None
):
    created_by_uid = None
    if data_element_tuple.created_by:
        created_by_user = get_user_by_name(
            data_element_tuple.created_by, session=session
        )
        if not created_by_user:
            LOG.error(
                f"Can't find created_by of data element {data_element_tuple.name}: {data_element_tuple.created_by}"
            )
        else:
            created_by_uid = created_by_user.id

    data_element = get_data_element_by_name(data_element_tuple.name, session=session)
    fields = {
        **data_element_tuple._asdict(),
        "metastore_id": metastore_id,
        "created_by": created_by_uid,
    }

    if not data_element:
        # create a new data element
        data_element = DataElement.create(fields=fields, commit=commit, session=session)
    else:
        # update the data element
        data_element = DataElement.update(
            id=data_element.id, fields=fields, commit=commit, session=session
        )

    if commit:
        session.commit()
    else:
        session.flush()

    return data_element


@with_session
def create_data_element_association(
    metastore_id: int,
    data_element_tuple: Union[DataElementTuple, str],
    column_id: int,
    association_type: DataElementAssociationType,
    property_name: DataElementAssociationProperty,
    primitive_type: str = None,
    session=None,
):
    if not data_element_tuple and not primitive_type:
        raise Exception(
            f"Can not create DataElementAssociation: {data_element_tuple} is not a valid data element and primitive type is empty"
        )

    data_element = None
    if data_element_tuple:
        if type(data_element_tuple) is str:
            data_element = get_data_element_by_name(data_element_tuple, session=session)
        elif data_element_tuple.name and data_element_tuple.type:
            data_element = create_or_update_data_element(
                metastore_id, data_element_tuple, session=session
            )

    return DataElementAssociation(
        column_id=column_id,
        type=association_type,
        property_name=property_name.value,
        data_element_id=data_element.id if data_element is not None else None,
        primitive_type=primitive_type,
    )


@with_session
def create_column_data_element_association(
    metastore_id: int,
    column_id: int,
    data_element_association: DataElementAssociationTuple,
    commit=True,
    session=None,
):
    """This function is used for loading column tags from metastore."""
    # delete the current data element association of the column
    session.query(DataElementAssociation).filter_by(column_id=column_id).delete()

    if data_element_association is not None:
        try:
            value_association = create_data_element_association(
                metastore_id=metastore_id,
                data_element_tuple=data_element_association.value_data_element,
                column_id=column_id,
                association_type=data_element_association.type,
                property_name=DataElementAssociationProperty.VALUE,
                primitive_type=data_element_association.value_primitive_type,
                session=session,
            )

            if data_element_association.type == DataElementAssociationType.MAP:
                key_association = create_data_element_association(
                    metastore_id=metastore_id,
                    data_element_tuple=data_element_association.key_data_element,
                    column_id=column_id,
                    association_type=data_element_association.type,
                    property_name=DataElementAssociationProperty.KEY,
                    primitive_type=data_element_association.key_primitive_type,
                    session=session,
                )
                session.add(key_association)

            session.add(value_association)
        except Exception as e:
            LOG.error(e, exc_info=True)

    if commit:
        session.commit()
    else:
        session.flush()
