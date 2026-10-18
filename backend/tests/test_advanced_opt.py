"""
Tests for advanced optimization module.
"""

import pytest
import sys
import os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from optics.advanced_opt import (
    global_search, hybrid_optimize, OptimizationResult
)


class TestGlobalSearch:
    """Tests for global optimization."""
    
    def test_optimize_sphere(self):
        """Optimize sphere function."""
        def sphere(x):
            return sum(xi**2 for xi in x)
        
        result = global_search(sphere, [(-5, 5), (-5, 5)], method='de', maxiter=100, seed=42)
        assert result.success
        assert result.objective < 0.1  # Should find near-zero minimum
    
    def test_hybrid_optimize(self):
        """Test hybrid optimization."""
        def rosenbrock(x):
            return (1 - x[0])**2 + 100 * (x[1] - x[0]**2)**2
        
        result = hybrid_optimize(
            rosenbrock, [(-2, 2), (-2, 2)],
            maxiter_global=200, maxiter_local=200, seed=42
        )
        assert result.success
        # Global minimum at (1, 1)
        assert abs(result.params[0] - 1.0) < 0.5
        assert abs(result.params[1] - 1.0) < 0.5
    
    def test_pso(self):
        """Test PSO optimization."""
        def sphere(x):
            return sum(xi**2 for xi in x)
        
        result = global_search(sphere, [(-5, 5)]*3, method='pso', maxiter=50, seed=42)
        assert result.objective < 25.0
    
    def test_sa(self):
        """Test simulated annealing."""
        def sphere(x):
            return sum(xi**2 for xi in x)
        
        result = global_search(sphere, [(-5, 5)]*2, method='sa', maxiter=1000, seed=42)
        assert result.objective < 25.0
