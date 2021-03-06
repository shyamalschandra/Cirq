# Copyright 2018 The Cirq Developers
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Dict, Sequence, Tuple, TypeVar

from cirq import abc
from cirq.ops import (
        CompositeGate, Gate, QubitId, OP_TREE, SWAP,
        flatten_op_tree, GateOperation, TextDiagrammable,
        gate_features)

LogicalIndex = TypeVar('LogicalIndex', int, QubitId)
LogicalGates = Dict[Tuple[LogicalIndex, ...], Gate]
LogicalMappingKey = TypeVar('LogicalMappingKey', bound=QubitId)
LogicalMapping = Dict[LogicalMappingKey, LogicalIndex]

class PermutationGate(Gate, TextDiagrammable, metaclass=abc.ABCMeta):
    """A permutation gate indicates a change in the mapping from qubits to
    logical indices.

    Args:
        swap_gate: the gate that swaps the indices mapped to by a pair of
            qubits (e.g. SWAP or fermionic swap).
    """

    def __init__(self, swap_gate: Gate=SWAP) -> None:
        self.swap_gate = swap_gate


    @abc.abstractmethod
    def permutation(self, qubit_count: int) -> Dict[int, int]:
        """permutation = {i: s[i]} indicates that the i-th element is mapped to
        the s[i]-th element."""
        pass


    def update_mapping(self, mapping: Dict[QubitId, LogicalIndex],
                       keys: Sequence[QubitId]
                       ) -> None:
        """Updates a mapping (in place) from qubits to logical indices.

        Args:
            mapping: The mapping to update.
            keys: The qubits acted on by the gate.
        """
        n_elements = len(keys)
        permutation = self.permutation(n_elements)
        indices = tuple(permutation.keys())
        new_keys = [keys[permutation[i]] for i in indices]
        old_elements = [mapping[keys[i]] for i in indices]
        mapping.update(zip(new_keys, old_elements))


    @staticmethod
    def validate_permutation(permutation: Dict[int, int],
                             n_elements: int=None) -> None:
        if not permutation:
            return
        if set(permutation.values()) != set(permutation):
            raise IndexError('key and value sets must be the same.')
        if min(permutation) < 0:
            raise IndexError('keys of the permutation must be non-negative.')
        if n_elements is not None:
            if max(permutation) >= n_elements:
                raise IndexError('key is out of bounds.')

    def text_diagram_info(self, args: gate_features.TextDiagramInfoArgs
            ) -> gate_features.TextDiagramInfo:
        if args.known_qubit_count is None:
            return NotImplemented
        permutation = self.permutation(args.known_qubit_count)
        arrow = '↦' if args.use_unicode_characters else '->'
        wire_symbols = tuple(str(i) + arrow + str(permutation.get(i, i))
                        for i in range(args.known_qubit_count))
        return gate_features.TextDiagramInfo(wire_symbols=wire_symbols)


class SwapPermutationGate(PermutationGate, CompositeGate):
    """Generic swap gate."""

    def permutation(self, qubit_count: int) -> Dict[int, int]:
        return {0: 1, 1: 0}

    def default_decompose(
            self, qubits: Sequence[QubitId]) -> OP_TREE:
        yield self.swap_gate(*qubits)

class LinearPermutationGate(PermutationGate, CompositeGate):
    """A permutation gate that decomposes a given permutation using a linear
        sorting network."""

    def __init__(self,
                 permutation: Dict[int, int],
                 swap_gate: Gate=SWAP
                 ) -> None:
        """Initializes a linear permutation gate.

        Args:
            permutation: The permutation effected by the gate.
            swap_gate: The swap gate used in decompositions.
        """
        PermutationGate.validate_permutation(permutation)
        self._permutation = permutation
        self.swap_gate = swap_gate

    def permutation(self, qubit_count: int) -> Dict[int, int]:
        return self._permutation

    def default_decompose(self, qubits: Sequence[QubitId]) -> OP_TREE:
        swap_gate = SwapPermutationGate(self.swap_gate)
        n_qubits = len(qubits)
        mapping = {i: self._permutation.get(i, i) for i in range(n_qubits)}
        for layer_index in range(n_qubits):
            for i in range(layer_index % 2, n_qubits - 1, 2):
                if mapping[i] > mapping[i + 1]:
                    yield swap_gate(*qubits[i:i+2])
                    mapping[i], mapping[i+1] = mapping[i+1], mapping[i]

def update_mapping(mapping: Dict[QubitId, LogicalIndex],
                   operations: OP_TREE
                   ) -> None:
    """Updates a mapping (in place) from qubits to logical indices according to
    a set of permutation gates. Any gates other than permutation gates are
    ignored.

    Args:
        mapping: The mapping to update.
        operations: The operations to update according to.
    """
    for op in flatten_op_tree(operations):
        if (isinstance(op, GateOperation) and
            isinstance(op.gate, PermutationGate)):
            op.gate.update_mapping(mapping, op.qubits)
