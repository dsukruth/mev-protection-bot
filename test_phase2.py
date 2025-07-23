#!/usr/bin/env python3
"""
Test script to verify Phase 2 integration works correctly
"""
import sys
import os
sys.path.append('.')

def test_imports():
    """Test that all Phase 2 components can be imported"""
    try:
        from src.attack_detector import AttackDetector, SandwichAttack
        from src.ml_detector import MLAttackDetector
        from src.multichain_monitor import MultiChainMonitor
        print("✅ All Phase 2 imports successful")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def test_ml_integration():
    """Test ML detector integration"""
    try:
        from src.attack_detector import AttackDetector
        detector = AttackDetector()
        
        if hasattr(detector, 'ml_detector'):
            print("✅ ML detector integrated into AttackDetector")
            return True
        else:
            print("❌ ML detector not found in AttackDetector")
            return False
    except Exception as e:
        print(f"❌ ML integration error: {e}")
        return False

def test_sandwich_attack_fields():
    """Test that SandwichAttack has new Phase 2 fields"""
    try:
        from src.attack_detector import SandwichAttack, PendingTransaction
        
        dummy_tx = PendingTransaction(
            tx_hash="0x123",
            from_address="0x456",
            to_address="0x789",
            gas_price=1000000000,
            decoded_data={},
            timestamp=1234567890,
            token_pair=("0xA", "0xB"),
            estimated_value=1000,
            slippage=1.0
        )
        
        attack = SandwichAttack(
            victim_tx=dummy_tx,
            front_run_tx=None,
            back_run_tx=None,
            estimated_profit=100.0,
            estimated_victim_loss=50.0,
            confidence_score=0.8,
            chain="ethereum",
            ml_score=0.75,
            risk_level="HIGH"
        )
        
        if hasattr(attack, 'chain') and hasattr(attack, 'ml_score') and hasattr(attack, 'risk_level'):
            print("✅ SandwichAttack has all Phase 2 fields")
            return True
        else:
            print("❌ SandwichAttack missing Phase 2 fields")
            return False
    except Exception as e:
        print(f"❌ SandwichAttack test error: {e}")
        return False

def test_multichain_monitor():
    """Test MultiChainMonitor initialization"""
    try:
        from src.multichain_monitor import MultiChainMonitor
        
        def dummy_callback(decoded_tx, estimated_value, slippage):
            pass
            
        monitor = MultiChainMonitor(on_transaction_callback=dummy_callback)
        
        if hasattr(monitor, 'chains') and len(monitor.chains) > 1:
            print("✅ MultiChainMonitor supports multiple chains")
            return True
        else:
            print("❌ MultiChainMonitor not properly configured")
            return False
    except Exception as e:
        print(f"❌ MultiChainMonitor test error: {e}")
        return False

def main():
    """Run all Phase 2 tests"""
    print("🧪 Testing Phase 2 Implementation...")
    print("=" * 50)
    
    tests = [
        test_imports,
        test_ml_integration,
        test_sandwich_attack_fields,
        test_multichain_monitor
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print("=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 Phase 2 integration successful!")
        return True
    else:
        print("❌ Phase 2 integration has issues")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
