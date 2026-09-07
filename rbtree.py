# Copyright (c) 2026 Thales
# This software is released under the MIT License.
# See the LICENSE file in the project root for full license information.

from enum import Enum

class RBNode:
    def __init__(self, vcpu):
        self.vcpu = vcpu
        self.periodicity = vcpu.period
        self.left = None
        self.right = None
        self.parent = None
        self.color = RBTree.Color.RED  # New nodes are red by default

class RBTree:
    class Color(Enum):
            RED = 0
            BLACK = 1
    def __init__(self):
        self.root = None

    def rb_first(self):
        n = self.root
        if not n:
            return None
        while n.left:
            n = n.left
        return n

    def left_rotate(self, x):
        y = x.right
        x.right = y.left
        if y.left: y.left.parent = x
        y.parent = x.parent
        if not x.parent: self.root = y
        elif x == x.parent.left: x.parent.left = y
        else: x.parent.right = y
        y.left = x
        x.parent = y

    def right_rotate(self, x):
        y = x.left
        x.left = y.right
        if y.right: y.right.parent = x
        y.parent = x.parent
        if not x.parent: self.root = y
        elif x == x.parent.right: x.parent.right = y
        else: x.parent.left = y
        y.right = x
        x.parent = y

    def insert(self, vcpu):
        node = RBNode(vcpu)
        y = None
        x = self.root
        
        # 1. Classic binary search tree insertion based on periodicity
        while x:
            y = x
            if node.periodicity < x.periodicity:
                x = x.left
            else:
                x = x.right
                
        node.parent = y
        if not y: self.root = node
        elif node.periodicity < y.periodicity: y.left = node
        else: y.right = node
            
        # 2. Fix the red-black tree properties after insertion
        if not node.parent or not node.parent.parent:
            if not node.parent: node.color = RBTree.Color.BLACK
            return
            
        self._fix_insert(node)

    def _fix_insert(self, k):
        while k.parent.color == RBTree.Color.RED:
            if k.parent == k.parent.parent.left:
                u = k.parent.parent.right
                if u and u.color == RBTree.Color.RED:
                    u.color, k.parent.color = RBTree.Color.BLACK, RBTree.Color.BLACK
                    k.parent.parent.color = RBTree.Color.RED
                    k = k.parent.parent
                else:
                    if k == k.parent.right:
                        k = k.parent
                        self.left_rotate(k)
                    k.parent.color = RBTree.Color.BLACK
                    k.parent.parent.color = RBTree.Color.RED
                    self.right_rotate(k.parent.parent)
            else:
                u = k.parent.parent.left
                if u and u.color == RBTree.Color.RED:
                    u.color, k.parent.color = RBTree.Color.BLACK, RBTree.Color.BLACK
                    k.parent.parent.color = RBTree.Color.RED
                    k = k.parent.parent
                else:
                    if k == k.parent.left:
                        k = k.parent
                        self.right_rotate(k)
                    k.parent.color = RBTree.Color.BLACK
                    k.parent.parent.color = RBTree.Color.RED
                    self.left_rotate(k.parent.parent)
            if k == self.root: break
        self.root.color = RBTree.Color.BLACK

    def remove(self, vcpu):
        node = self.root
        while node:
            if vcpu == node.vcpu:
                break
            elif vcpu.periodicity < node.periodicity:
                node = node.left
            else:
                node = node.right
                
        if not node: return
        if not node.left and not node.right:
            if node.parent:
                if node == node.parent.left: node.parent.left = None
                else: node.parent.right = None
            else: self.root = None
        elif not node.right or not node.left:
            child = node.left if node.left else node.right
            if node.parent:
                if node == node.parent.left: node.parent.left = child
                else: node.parent.right = child
            else: self.root = child
            child.parent = node.parent
        else:
            successor = node.right
            while successor.left: successor = successor.left
            node.vcpu, node.periodicity = successor.vcpu, successor.periodicity
            if successor == successor.parent.left: successor.parent.left = successor.right
            else: successor.parent.right = successor.right
            if successor.right: successor.right.parent = successor.parent