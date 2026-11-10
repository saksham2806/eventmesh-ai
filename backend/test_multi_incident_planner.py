import unittest
from multi_incident_planner import plan_multi_disruption, to_minutes

class MultiIncidentTests(unittest.TestCase):
    def setUp(self):
        self.session = {'id':2,'title':'AI Keynote','room':'Hall A','speaker':'Rahul','start_time':'10:00','end_time':'11:00'}
        self.rooms = [{'id':1,'name':'Hall A','capacity':100},{'id':2,'name':'Hall B','capacity':60},{'id':3,'name':'Hall C','capacity':80},{'id':4,'name':'Hall D','capacity':40}]
        self.bookings=[{'id':3,'room':'Hall B','speaker':'Priya','start_time':'10:00','end_time':'11:00'}]
    def test_room_and_delay_both_honored(self):
        result=plan_multi_disruption(self.session, self.rooms,self.bookings,[{'type':'ROOM_UNAVAILABLE','room':'Hall A'},{'type':'SPEAKER_DELAY','delay_minutes':45}],50)
        self.assertEqual(result['status'],'CANDIDATES_PREVIEW')
        for proposal in result['candidates']:
            self.assertNotEqual(proposal['room'],'Hall A')
            self.assertGreaterEqual(to_minutes(proposal['start_time']),to_minutes('10:45'))
            self.assertNotEqual(proposal['room'],'Hall D')
    def test_cancellation_review_only(self):
        result=plan_multi_disruption(self.session,self.rooms,self.bookings,[{'type':'SESSION_CANCELLED'}],50)
        self.assertEqual(result['status'],'CANCELLATION_REVIEW')
        self.assertFalse(result['candidates'])
    def test_unknown_room_rejected(self):
        with self.assertRaises(ValueError):
            plan_multi_disruption(self.session,self.rooms,self.bookings,[{'type':'ROOM_UNAVAILABLE','room':'Hall Z'}],50)
    def test_no_issue_affecting_session(self):
        result=plan_multi_disruption(self.session,self.rooms,self.bookings,[{'type':'ROOM_UNAVAILABLE','room':'Hall C'}],50)
        self.assertEqual(result['status'],'NO_SCHEDULE_CHANGE_REQUIRED')
    def test_never_recommends_room_conflict(self):
        result=plan_multi_disruption(self.session,self.rooms,self.bookings,[{'type':'ROOM_UNAVAILABLE','room':'Hall A'}],50)
        for proposal in result['candidates']:
            self.assertFalse(proposal['room'] == 'Hall B' and proposal['start_time']=='10:00')

if __name__=='__main__':
    unittest.main()
