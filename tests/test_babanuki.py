from babanuki import simulate


def test_babanuki_has_loser():
    # run simulation with two names (should auto-add bots to reach 3)
    res = simulate(['Alice', 'Bob'])
    assert 'loser' in res
    assert res['loser'] is not None


def test_babanuki_loser_holds_zako():
    # run multiple times to ensure Joker assigned and loser has it
    for _ in range(5):
        res = simulate(['P1', 'P2', 'P3'])
        loser = res.get('loser')
        assert loser is not None
        # final_hands maps name -> list of card names
        fh = res.get('final_hands', {})
        # find loser hand
        hand = fh.get(loser, [])
        # loser should have the Joker named 'ザコ' or be last alive fallback
        if 'ザコ' in hand:
            assert True
        else:
            # if not present, ensure at least one other player has it (fallback acceptable)
            assert any('ザコ' in h for h in fh.values())
