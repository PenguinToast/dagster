from abc import ABCMeta, abstractmethod
from collections import namedtuple

import six

from dagster import check


from .execution_context import SystemPipelineExecutionContext
from .object_store import ObjectStore
from .types.runtime import RuntimeType


class StepOutputHandle(namedtuple('_StepOutputHandle', 'step_key output_name')):
    @staticmethod
    def from_step(step, output_name='result'):
        from .execution_plan.objects import ExecutionStep

        check.inst_param(step, 'step', ExecutionStep)

        return StepOutputHandle(step.key, output_name)

    def __new__(cls, step_key, output_name='result'):
        return super(StepOutputHandle, cls).__new__(
            cls,
            step_key=check.str_param(step_key, 'step_key'),
            output_name=check.str_param(output_name, 'output_name'),
        )


class IntermediatesManager(six.with_metaclass(ABCMeta)):  # pylint: disable=no-init
    @abstractmethod
    def get_intermediate(self, context, runtime_type, step_output_handle):
        pass

    @abstractmethod
    def set_intermediate(self, context, runtime_type, step_output_handle, value):
        pass

    @abstractmethod
    def has_intermediate(self, context, step_output_handle):
        pass

    @abstractmethod
    def copy_intermediate_from_prev_run(self, context, previous_run_id, step_output_handle):
        pass

    def all_inputs_covered(self, context, step):
        from .execution_plan.objects import ExecutionStep

        check.inst_param(step, 'step', ExecutionStep)
        for step_input in step.step_inputs:
            if not self.has_intermediate(context, step_input.prev_output_handle):
                return False
        return True


class InMemoryIntermediatesManager(IntermediatesManager):
    def __init__(self):
        self.values = {}

    def get_intermediate(self, context, runtime_type, step_output_handle):
        check.inst_param(step_output_handle, 'step_output_handle', StepOutputHandle)
        return self.values[step_output_handle]

    def set_intermediate(self, context, runtime_type, step_output_handle, value):
        check.inst_param(step_output_handle, 'step_output_handle', StepOutputHandle)
        self.values[step_output_handle] = value

    def has_intermediate(self, context, step_output_handle):
        check.inst_param(step_output_handle, 'step_output_handle', StepOutputHandle)
        return step_output_handle in self.values

    def copy_intermediate_from_prev_run(self, context, previous_run_id, step_output_handle):
        check.failed('not implemented in in memory')


class ObjectStoreIntermediatesManager(IntermediatesManager):
    def __init__(self, object_store):
        self._object_store = check.inst_param(object_store, 'object_store', ObjectStore)

    def _get_paths(self, step_output_handle):
        return ['intermediates', step_output_handle.step_key, step_output_handle.output_name]

    def get_intermediate(self, context, runtime_type, step_output_handle):
        check.inst_param(context, 'context', SystemPipelineExecutionContext)
        check.inst_param(runtime_type, 'runtime_type', RuntimeType)
        check.inst_param(step_output_handle, 'step_output_handle', StepOutputHandle)
        check.invariant(self.has_intermediate(context, step_output_handle))

        return self._object_store.get_object(
            context=context, runtime_type=runtime_type, paths=self._get_paths(step_output_handle)
        )

    def set_intermediate(self, context, runtime_type, step_output_handle, value):
        check.inst_param(context, 'context', SystemPipelineExecutionContext)
        check.inst_param(runtime_type, 'runtime_type', RuntimeType)
        check.inst_param(step_output_handle, 'step_output_handle', StepOutputHandle)
        check.invariant(not self.has_intermediate(context, step_output_handle))

        return self._object_store.set_object(
            obj=value,
            context=context,
            runtime_type=runtime_type,
            paths=self._get_paths(step_output_handle),
        )

    def has_intermediate(self, context, step_output_handle):
        check.inst_param(context, 'context', SystemPipelineExecutionContext)
        check.inst_param(step_output_handle, 'step_output_handle', StepOutputHandle)

        return self._object_store.has_object(context, self._get_paths(step_output_handle))

    def copy_intermediate_from_prev_run(self, context, previous_run_id, step_output_handle):
        return self._object_store.copy_object_from_prev_run(
            context, previous_run_id, self._get_paths(step_output_handle)
        )
