"""
Tests for CAD file import.
"""

import pytest
import sys
import os
import tempfile
import struct

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from optics.nsc.cad import (
    Mesh, Triangle, Vertex,
    import_stl, import_obj, import_cad_file,
    get_supported_formats
)


class TestVertex:
    """Tests for Vertex class."""
    
    def test_vertex_creation(self):
        v = Vertex(1.0, 2.0, 3.0)
        assert v.x == 1.0
        assert v.y == 2.0
        assert v.z == 3.0
    
    def test_to_vector(self):
        from optics.nsc.system import Vector3
        v = Vertex(1.0, 2.0, 3.0)
        vec = v.to_vector()
        assert isinstance(vec, Vector3)
        assert vec.x == 1.0


class TestTriangle:
    """Tests for Triangle class."""
    
    def test_triangle_creation(self):
        tri = Triangle(
            v0=Vertex(0, 0, 0),
            v1=Vertex(1, 0, 0),
            v2=Vertex(0, 1, 0)
        )
        assert tri.normal is not None
        # Normal should point in +z direction
        assert tri.normal.z > 0
    
    def test_ray_intersection(self):
        from optics.nsc.system import Ray, Vector3
        
        tri = Triangle(
            v0=Vertex(0, 0, 10),
            v1=Vertex(5, 0, 10),
            v2=Vertex(0, 5, 10)
        )
        
        ray = Ray(
            origin=Vector3(0, 0, 0),
            direction=Vector3(0, 0, 1)
        )
        
        result = tri.intersect(ray)
        assert result is not None
        t, normal = result
        assert t == pytest.approx(10.0, abs=0.01)
    
    def test_ray_miss(self):
        from optics.nsc.system import Ray, Vector3
        
        tri = Triangle(
            v0=Vertex(0, 0, 10),
            v1=Vertex(5, 0, 10),
            v2=Vertex(0, 5, 10)
        )
        
        ray = Ray(
            origin=Vector3(100, 100, 0),
            direction=Vector3(0, 0, 1)
        )
        
        result = tri.intersect(ray)
        assert result is None


class TestMesh:
    """Tests for Mesh class."""
    
    def test_mesh_creation(self):
        mesh = Mesh(name="Test")
        assert mesh.num_triangles == 0
        assert mesh.num_vertices == 0
    
    def test_add_triangle(self):
        mesh = Mesh(name="Test")
        tri = Triangle(
            v0=Vertex(0, 0, 0),
            v1=Vertex(1, 0, 0),
            v2=Vertex(0, 1, 0)
        )
        mesh.add_triangle(tri)
        assert mesh.num_triangles == 1
    
    def test_mesh_intersection(self):
        mesh = Mesh(name="Test")
        tri = Triangle(
            v0=Vertex(0, 0, 10),
            v1=Vertex(5, 0, 10),
            v2=Vertex(0, 5, 10)
        )
        mesh.add_triangle(tri)
        
        from optics.nsc.system import Ray, Vector3
        ray = Ray(
            origin=Vector3(0, 0, 0),
            direction=Vector3(0, 0, 1)
        )
        
        hit = mesh.intersect(ray)
        assert hit is not None
        assert hit.point.z == pytest.approx(10.0, abs=0.01)


class TestSTLImport:
    """Tests for STL file import."""
    
    def test_import_ascii_stl(self):
        """Test importing ASCII STL."""
        # Create a simple ASCII STL file
        stl_content = """solid test
  facet normal 0 0 1
    outer loop
      vertex 0 0 0
      vertex 1 0 0
      vertex 0 1 0
    endloop
  endfacet
endsolid test
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.stl', delete=False) as f:
            f.write(stl_content)
            f.flush()
            
            mesh = import_stl(f.name)
            assert mesh.num_triangles == 1
        
        os.unlink(f.name)
    
    def test_import_binary_stl(self):
        """Test importing binary STL."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.stl', delete=False) as f:
            # Header (80 bytes)
            f.write(b'\x00' * 80)
            
            # Number of triangles (1)
            f.write(struct.pack('<I', 1))
            
            # Normal (0, 0, 1)
            f.write(struct.pack('<3f', 0, 0, 1))
            
            # Vertices (triangle)
            f.write(struct.pack('<3f', 0, 0, 0))
            f.write(struct.pack('<3f', 1, 0, 0))
            f.write(struct.pack('<3f', 0, 1, 0))
            
            # Attribute byte count
            f.write(struct.pack('<H', 0))
            
            f.flush()
            
            mesh = import_stl(f.name)
            assert mesh.num_triangles == 1
        
        os.unlink(f.name)


class TestOBJImport:
    """Tests for OBJ file import."""
    
    def test_import_obj(self):
        """Test importing OBJ file."""
        obj_content = """# Simple triangle
v 0 0 0
v 1 0 0
v 0 1 0
f 1 2 3
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.obj', delete=False) as f:
            f.write(obj_content)
            f.flush()
            
            mesh = import_obj(f.name)
            assert mesh.num_triangles == 1
        
        os.unlink(f.name)


class TestCADImport:
    """Tests for generic CAD import."""
    
    def test_import_stl_file(self):
        """Test importing STL via generic importer."""
        stl_content = """solid test
  facet normal 0 0 1
    outer loop
      vertex 0 0 0
      vertex 1 0 0
      vertex 0 1 0
    endloop
  endfacet
endsolid test
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.stl', delete=False) as f:
            f.write(stl_content)
            f.flush()
            
            mesh = import_cad_file(f.name)
            assert mesh.num_triangles == 1
        
        os.unlink(f.name)
    
    def test_get_supported_formats(self):
        """Test getting supported formats."""
        formats = get_supported_formats()
        assert 'stl' in formats
        assert 'obj' in formats
        assert 'step' in formats
        assert 'iges' in formats
