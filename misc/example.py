from model import SpaceflightSimAPI
from poliastro.bodies import Earth, Mars
from poliastro.twobody import Orbit
from astropy import units as u
import numpy as np
import logging
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def test_basic_functionality():
    """Test basic simulation functionality."""
    print("\n=== Testing Basic Functionality ===")
    api = SpaceflightSimAPI()

    # Add spacecraft
    initial_orbit = Orbit.circular(Earth, alt=400 * u.km)
    api.add_spacecraft("Voyager", initial_orbit, mass=722 * u.kg)

    # Propagate
    api.propagate_system(1 * u.hour)

    # Get state
    state = api.get_spacecraft_state("Voyager")
    print(f"Position: {state.position} km")
    print(f"Velocity: {state.velocity} km/s")
    print(f"Mass: {state.mass} kg")

    return api


def test_maneuvers(api):
    """Test spacecraft maneuvers."""
    print("\n=== Testing Maneuvers ===")

    # Apply maneuver
    api.apply_spacecraft_maneuver("Voyager", np.array([0.1, 0.1, 0.0]))
    state = api.get_spacecraft_state("Voyager")
    print(f"New velocity: {state.velocity} km/s")
    print(f"New mass: {state.mass} kg")


def test_solar_system(api):
    """Test solar system functionality."""
    print("\n=== Testing Solar System ===")

    # Test body states
    earth_state = api.get_body_state("Earth")
    print(f"Earth position: {earth_state.position} km")
    print(f"Earth velocity: {earth_state.velocity} km/s")

    # Test relative positions
    rel_pos = api.get_relative_position("Earth", "Moon")
    print(f"Earth-Moon distance: {np.linalg.norm(rel_pos):.0f} km")


def test_performance():
    """Test simulation performance."""
    print("\n=== Testing Performance ===")
    api = SpaceflightSimAPI()

    # Add multiple spacecraft
    for i in range(5):
        orbit = Orbit.circular(Earth, alt=(400 + i*50) * u.km)
        api.add_spacecraft(f"Sat{i}", orbit, mass=500 * u.kg)

    # Time propagation
    start_time = time.time()
    api.propagate_system(1 * u.day)
    elapsed = time.time() - start_time

    print(f"Propagated 5 spacecraft for 1 day in {elapsed:.4f} seconds")
    print(f"Simulation time: {api.simulation_time}")


def main():
    """Run all tests."""
    api = test_basic_functionality()
    test_maneuvers(api)
    test_solar_system(api)
    test_performance()


if __name__ == "__main__":
    main()
