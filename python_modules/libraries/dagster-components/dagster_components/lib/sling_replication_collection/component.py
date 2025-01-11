from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Optional, Union

from dagster._core.definitions.assets import AssetsDefinition
from dagster._core.definitions.definitions_class import Definitions
from dagster._core.definitions.events import AssetMaterialization
from dagster._core.definitions.result import MaterializeResult
from dagster_embedded_elt.sling import DagsterSlingTranslator, SlingResource, sling_assets
from dagster_embedded_elt.sling.resources import AssetExecutionContext
from pydantic import BaseModel
from typing_extensions import Self

from dagster_components import Component, ComponentLoadContext
from dagster_components.core.component import component_type
from dagster_components.core.component_generator import ComponentGenerator
from dagster_components.core.dsl_schema import (
    AssetAttributesModel,
    AssetSpecTransform,
    OpSpecBaseModel,
)
from dagster_components.utils import get_wrapped_translator_class


class SlingReplicationParams(BaseModel):
    path: str
    op: Optional[OpSpecBaseModel] = None
    asset_attributes: Optional[AssetAttributesModel] = None


class SlingReplicationCollectionParams(BaseModel):
    sling: Optional[SlingResource] = None
    replications: Sequence[SlingReplicationParams]
    transforms: Optional[Sequence[AssetSpecTransform]] = None


@component_type(name="sling_replication_collection")
class SlingReplicationCollectionComponent(Component):
    def __init__(
        self,
        dirpath: Path,
        resource: SlingResource,
        sling_replications: Sequence[SlingReplicationParams],
        transforms: Sequence[AssetSpecTransform],
    ):
        self.dirpath = dirpath
        self.resource = resource
        self.sling_replications = sling_replications
        self.transforms = transforms

    @classmethod
    def get_generator(cls) -> ComponentGenerator:
        from dagster_components.lib.sling_replication_collection.generator import (
            SlingReplicationComponentGenerator,
        )

        return SlingReplicationComponentGenerator()

    @classmethod
    def get_component_schema_type(cls):
        return SlingReplicationCollectionParams

    @classmethod
    def load(cls, context: ComponentLoadContext) -> Self:
        loaded_params = context.load_params(cls.get_component_schema_type())
        return cls(
            dirpath=context.path,
            resource=loaded_params.sling or SlingResource(),
            sling_replications=loaded_params.replications,
            transforms=loaded_params.transforms or [],
        )

    def build_replication_asset(
        self, context: ComponentLoadContext, replication: SlingReplicationParams
    ) -> AssetsDefinition:
        translator_cls = get_wrapped_translator_class(DagsterSlingTranslator)

        @sling_assets(
            name=replication.op.name if replication.op else Path(replication.path).stem,
            op_tags=replication.op.tags if replication.op else {},
            replication_config=self.dirpath / replication.path,
            dagster_sling_translator=translator_cls(
                obj_name="stream_definition",
                base_translator=DagsterSlingTranslator(),
                asset_attributes=replication.asset_attributes or AssetAttributesModel(),
                value_renderer=context.templated_value_renderer,
            ),
        )
        def _asset(context: AssetExecutionContext):
            yield from self.execute(context=context, sling=self.resource)

        return _asset

    def execute(
        self, context: AssetExecutionContext, sling: SlingResource
    ) -> Iterator[Union[AssetMaterialization, MaterializeResult]]:
        yield from sling.replicate(context=context)

    def build_defs(self, context: ComponentLoadContext) -> Definitions:
        defs = Definitions(
            assets=[
                self.build_replication_asset(context, replication)
                for replication in self.sling_replications
            ],
        )
        for transform in self.transforms:
            defs = transform.apply(defs, context.templated_value_renderer)
        return defs
