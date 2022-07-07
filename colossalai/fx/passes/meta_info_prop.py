import torch
import torch.fx
from torch.fx.node import Node, map_aggregate
from typing import Any, Tuple, NamedTuple, Optional, Dict
from functools import reduce
from torch.fx._compatibility import compatibility


@compatibility(is_backward_compatible=True)
class TensorMetadata(NamedTuple):
    # TensorMetadata is a structure containing pertinent information
    # about a tensor within a PyTorch program.

    shape: torch.Size
    dtype: torch.dtype
    requires_grad: bool
    stride: Tuple[int]
    numel: int
    # TODO: we can add a list of sharding spec here, and record the sharding
    # behaviour by appending sharding spec into list.


def _extract_tensor_metadata(result: torch.Tensor) -> TensorMetadata:
    """
    Extract a TensorMetadata NamedTuple describing `result`.
    """
    shape = result.shape
    dtype = result.dtype
    requires_grad = result.requires_grad
    stride = result.stride()
    numel = result.numel()

    return TensorMetadata(shape, dtype, requires_grad, stride, numel)


@compatibility(is_backward_compatible=True)
class MetaInfoProp(torch.fx.Interpreter):
    """
    Execute an FX graph Node-by-Node and
    record the shape and type of the result
    into the corresponding node.

    Usage:
        BATCH_SIZE = 2
        DIM_IN = 4
        DIM_OUT = 16
        model = torch.nn.Linear(DIM_IN, DIM_OUT)
        input_sample = torch.rand(BATCH_SIZE, DIM_IN)
        orig_output = model(input_sample)
        gm = symbolic_trace(model)
        MetaInfoProp(gm).run(input_sample)

        for node in gm.graph.nodes:
            print(node.name, node.meta['tensor_meta'].dtype,
                node.meta['tensor_meta'].shape, node.meta['tensor_meta'].numel)
        
        # output of above code is 
        # input_1 torch.float32 torch.Size([2, 4]) 8
        # weight torch.float32 torch.Size([16, 4]) 64
        # bias torch.float32 torch.Size([16]) 16
        # linear torch.float32 torch.Size([2, 16]) 32
        # output torch.float32 torch.Size([2, 16]) 32
    Args:
         module (GraphModule): The module to be executed

    """

    def run_node(self, n: Node) -> Any:
        result = super().run_node(n)

        found_tensor = False

        def extract_tensor_meta(obj):
            if isinstance(obj, torch.Tensor):
                nonlocal found_tensor
                found_tensor = True
                return _extract_tensor_metadata(obj)
            else:
                return obj

        meta = map_aggregate(result, extract_tensor_meta)
        if found_tensor:
            n.meta['tensor_meta'] = meta
        else:
            n.meta['tensor_meta'] = TensorMetadata(None, None, False, None, 0)

        n.meta['type'] = type(result)
        return result

    def propagate(self, *args):
        """
        Run `module` via interpretation and return the result and
        record the shape and type of each node.

        Args:
            *args (Tensor): the sample input.

        Returns:
            Any: The value returned from executing the Module
        """
        return super().run(*args)