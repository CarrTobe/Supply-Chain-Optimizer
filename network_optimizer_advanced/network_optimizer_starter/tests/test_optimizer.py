import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from optimizer import defaults, solve_network, benchmark_scenarios


class NetworkTests(unittest.TestCase):
    def test_default_solution_satisfies_all_markets(self):
        r=solve_network(*defaults())
        self.assertEqual(r['demand'],11500)
        self.assertEqual(r['unserved'],0)
        self.assertEqual(sum(row['Allocated'] for row in r['center_results']),r['shipped'])
        self.assertAlmostEqual(r['total_cost'],sum(r['breakdown'].values()),places=5)
        self.assertAlmostEqual(r['total_cost'],r['raw_objective'],places=4)

    def test_newark_outage_causes_shortfall(self):
        centers, markets=defaults()
        centers[-1]['Available']=False
        r=solve_network(centers,markets)
        self.assertEqual(r['unserved'],400)
        self.assertTrue(all(row['Allocated']<=row['Capacity'] for row in r['center_results']))

    def test_weather_is_costlier_than_baseline(self):
        centers, markets=defaults()
        baseline=solve_network(centers,markets)
        storm=solve_network(centers,markets,weather_center='Atlanta',weather_severity='Severe disruption')
        self.assertGreater(storm['total_cost'],baseline['total_cost'])

    def test_demand_and_total_balance(self):
        r=solve_network(*defaults(),demand_change_pct=15)
        self.assertEqual(r['shipped']+r['unserved'],r['demand'])
        self.assertEqual(r['demand'],13225)

    def test_scenarios(self):
        scenarios=benchmark_scenarios()
        self.assertEqual(len(scenarios),6)
        self.assertEqual(scenarios[0]['Unserved'],0)
        self.assertEqual(scenarios[-1]['Unserved'],400)


if __name__=='__main__': unittest.main()
