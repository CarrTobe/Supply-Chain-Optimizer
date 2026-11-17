import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from optimizer import defaults, solve_network, default_settings, default_lanes, benchmark_scenarios


class AdvancedNetworkTests(unittest.TestCase):
    def setUp(self):
        self.c,self.m=defaults()
        self.s=default_settings()

    def solve(self, **settings):
        ss={**self.s,**settings}
        return solve_network(self.c,self.m,ss)

    def test_baseline_demand_conservation_and_cost(self):
        r=self.solve()
        self.assertEqual(r['demand'],11500)
        self.assertEqual(r['shipped']+r['unserved'],r['demand'])
        self.assertEqual(r['unserved'],0)
        self.assertAlmostEqual(r['total_cost'],sum(r['breakdown'].values()),places=5)
        self.assertAlmostEqual(r['total_cost'],r['raw_objective'],places=5)
        self.assertEqual(sum(x['Units'] for x in r['allocations']),r['shipped'])
        self.assertEqual(sum(x['Trucks dispatched'] for x in r['allocations']),r['trucks'])
        for c in r['center_results']:
            self.assertLessEqual(c['Allocated'],c['Effective throughput capacity'])
            self.assertLessEqual(c['Safety stock units']+c['Cycle inventory units'],c['Storage capacity']+0.2)
        self.assertTrue(all((x['Truckload units']<=250*x['Trucks dispatched']) for x in r['allocations']))

    def test_safety_stock_toggle_and_holding(self):
        a=self.solve(safety_stock_enabled=True)
        b=self.solve(safety_stock_enabled=False)
        self.assertGreater(a['safety_stock_units'],0)
        self.assertAlmostEqual(b['safety_stock_units'],0)
        self.assertGreater(a['inventory_holding_cost'],b['inventory_holding_cost'])
        self.assertGreaterEqual(a['total_cost']+0.01,b['total_cost'])

    def test_lead_time_variability_affects_inventory(self):
        a=self.solve()
        for c in self.c:
            c['Lead SD days']+=4
        b=self.solve()
        self.assertGreater(b['safety_stock_units'],a['safety_stock_units'])

    def test_service_target_changes_safety_stock(self):
        a=self.solve(target_service_pct=90)
        b=self.solve(target_service_pct=99)
        self.assertGreater(b['safety_stock_units'],a['safety_stock_units'])

    def test_multiple_facility_and_market_disruptions(self):
        a=self.solve()
        for c in self.c:
            if c['Center'] in ('Chicago','Newark'): c['Weather']='Severe'
        self.m[0]['Weather']='Moderate'
        b=self.solve()
        self.assertGreater(b['total_cost'],a['total_cost'])
        self.assertTrue(any(x['Weather']=='Severe' for x in b['center_results']))
        self.assertGreater(b['safety_stock_units'],a['safety_stock_units'])

    def test_weather_intensity_zero_nullifies_weather_effect(self):
        a=self.solve()
        self.c[0]['Weather']='Extreme'
        b=self.solve(weather_intensity=0)
        self.assertAlmostEqual(a['total_cost'],b['total_cost'],delta=0.01)

    def test_construction_selected_for_closure(self):
        self.c[4]['Available']=False  # Newark closed
        r=self.solve()
        self.assertEqual(r['unserved'],0)
        self.assertTrue(r['built'])
        self.assertGreater(r['construction_capex'],0)

    def test_construction_not_allowed_shortfall(self):
        self.c[4]['Available']=False
        r=self.solve(construction_enabled=False)
        self.assertEqual(r['unserved'],400)
        self.assertEqual(r['built'],[])

    def test_construction_budget_limits_build(self):
        self.c[4]['Available']=False
        r=self.solve(construction_budget=0)
        self.assertEqual(r['built'],[])
        self.assertGreater(r['unserved'],0)

    def test_max_mileage_typed_limit(self):
        a=self.solve(max_road_miles=1.0)
        self.assertEqual(a['shipped'],0)
        self.assertEqual(a['unserved'],11500)
        b=self.solve(max_road_miles=20000.0)
        self.assertEqual(b['unserved'],0)

    def test_hard_fulfillment_can_be_infeasible(self):
        self.c[4]['Available']=False
        with self.assertRaisesRegex(RuntimeError,'Infeasible'):
            self.solve(construction_enabled=False,minimum_fulfillment_pct=100)

    def test_truckload_capacity_and_minimum_fill(self):
        a=self.solve(min_truck_fill_pct=90.0)
        for x in a['allocations']:
            if x['Trucks dispatched']:
                self.assertGreaterEqual(x['Truck fill %'],89.9)

    def test_no_truckload_uses_spot(self):
        r=self.solve(truckload_enabled=False)
        self.assertEqual(r['trucks'],0)
        self.assertEqual(r['truckload_units'],0)
        self.assertEqual(r['spot_units'],r['shipped'])

    def test_lane_overrides_block_and_limit(self):
        lanes=default_lanes(self.c,self.m)
        for lane in lanes:
            if lane['Market']=='Northeast / Boston':lane['Blocked']=True
        r=solve_network(self.c,self.m,self.s,lanes)
        self.assertGreaterEqual(r['unserved'],1700)
        self.assertTrue(all(x['Market']!='Northeast / Boston' for x in r['allocations']))
        lanes=default_lanes(self.c,self.m)
        lanes[0]['Road override miles']=20000
        s={**self.s,'max_road_miles':19000.0}
        r=solve_network(self.c,self.m,s,lanes)
        self.assertFalse(any(x['Center']=='Chicago' and x['Market']=='Northeast / Boston' for x in r['allocations']))

    def test_demand_growth_and_scenario_tests(self):
        r=self.solve(demand_change_pct=15)
        self.assertEqual(r['demand'],13225)
        scenarios=benchmark_scenarios()
        self.assertEqual(len(scenarios),8)
        self.assertEqual(scenarios[0]['Unserved'],0)
        self.assertTrue(any('Columbus' in x['Facilities built'] for x in scenarios))


if __name__=='__main__':unittest.main()
