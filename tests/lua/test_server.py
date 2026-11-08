import json
import os
import re
import unittest

from harness import Env, standard_players

# Old convars: still set on some servers. They must now be ignored: nothing is ever posted to Discord.
OLD_HOOKS = {
    "weazel_webhook_publish_1": "https://discord.test/api/webhooks/1/aaa",
    "weazel_webhook_publish_2": "https://discord.test/api/webhooks/2/bbb",
    "weazel_webhook_log": "https://discord.test/api/webhooks/3/ccc",
}
HOOKS = {}
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def env(**kw):
    e = Env(**kw)
    standard_players(e)
    return e


def job_json(name, level):
    return json.dumps({"name": name, "label": name, "payment": 10, "grade": {"level": level, "name": "x"}})


class ArticleAccess(unittest.TestCase):
    ROW = {"id": 5, "title": "T", "content": "C", "author": "Jo Journalist", "image": None, "status": "draft",
           "category": "breaking", "date": "01/01 00:00"}

    def test_public_cannot_read_draft_or_pending(self):
        for status in ("draft", "pending"):
            e = env()
            e.respond("query", "FROM rp_articles WHERE id=?", [dict(self.ROW, status=status)])
            e.fire("weazel:server:getArticle", 1, 5)
            self.assertEqual(e.sent("weazel:client:showArticle"), [], status)

    def test_public_can_read_published(self):
        e = env()
        e.respond("query", "FROM rp_articles WHERE id=?", [dict(self.ROW, status="published")])
        e.fire("weazel:server:getArticle", 1, 5)
        self.assertEqual(len(e.sent("weazel:client:showArticle", 1)), 1)

    def test_reporter_can_read_draft_but_intern_cannot_read_others_pending(self):
        e = env()
        e.respond("query", "FROM rp_articles WHERE id=?", [dict(self.ROW, status="draft")])
        e.fire("weazel:server:getArticle", 2, 5)
        self.assertEqual(len(e.sent("weazel:client:showArticle", 2)), 1)
        e = env()
        e.respond("query", "FROM rp_articles WHERE id=?", [dict(self.ROW, status="pending")])
        e.fire("weazel:server:getArticle", 2, 5)
        self.assertEqual(e.sent("weazel:client:showArticle"), [])
        e.fire("weazel:server:getArticle", 4, 5)  # editor
        self.assertEqual(len(e.sent("weazel:client:showArticle", 4)), 1)

    def test_comment_citizenid_not_sent_to_client(self):
        e = env()
        e.respond("query", "FROM rp_articles WHERE id=?", [dict(self.ROW, status="published")])
        e.respond("query", "FROM article_comments", [{"id": 1, "author_name": "A", "comment": "hi", "citizenid": "SECRET1", "date": "d"}])
        e.fire("weazel:server:getArticle", 1, 5)
        payload = json.dumps(e.sent("weazel:client:showArticle")[0][1])
        self.assertNotIn("SECRET1", payload)

    def test_public_access_can_be_disabled(self):
        e = env(convars={"weazel_public_access": "0"})
        e.fire("weazel:server:openPanel", 1)
        self.assertEqual(e.sent("weazel:client:open"), [])
        e.fire("weazel:server:openPanel", 3)
        self.assertEqual(len(e.sent("weazel:client:open", 3)), 1)

    def test_open_is_decided_by_server(self):
        e = env()
        e.fire("weazel:server:openPanel", 1)
        self.assertEqual(len(e.sent("weazel:client:open", 1)), 1)
        role = e.sent("weazel:client:setRole", 1)[0][1]
        self.assertEqual((role["role"], role["grade"]), ("unemployed", 0))


class Approval(unittest.TestCase):
    PENDING = [{"id": 9, "title": "News", "author": "Jo Journalist", "category": "crime", "content": "body", "image": None}]

    def test_approving_a_non_pending_article_does_nothing_and_leaks_nothing(self):
        e = env(convars=HOOKS)
        # id exists as a draft: the "pending" select returns nothing
        e.fire("weazel:server:approvePending", 4, 9)
        self.assertEqual([s for s in e.writes("rp_articles")], [])
        self.assertEqual(e.http, [])
        self.assertEqual(e.sent("weazel:client:articleNotification"), [])

    def test_approve_pending_publishes_and_notifies_once(self):
        e = env(convars=OLD_HOOKS)
        e.respond("query", "WHERE id=? AND status='pending'", self.PENDING)
        e.fire("weazel:server:approvePending", 4, 9)
        self.assertTrue(any("status='published'" in s for s in e.writes("rp_articles")))
        self.assertEqual(len(e.sent("weazel:client:articleNotification")), 8)  # every online player, once

    def test_below_editor_cannot_approve(self):
        for src in (1, 2, 3):
            e = env(convars=HOOKS)
            e.respond("query", "WHERE id=? AND status='pending'", self.PENDING)
            e.fire("weazel:server:approvePending", src, 9)
            self.assertEqual(e.writes("rp_articles"), [], src)

    def test_self_approval_block_is_opt_in(self):
        e = env(convars=dict(HOOKS, weazel_block_self_approval="1"))
        e.respond("query", "WHERE id=? AND status='pending'", [dict(self.PENDING[0], author="Ed Editor")])
        e.fire("weazel:server:approvePending", 4, 9)
        self.assertEqual(e.writes("rp_articles"), [])
        e = env(convars=HOOKS)
        e.respond("query", "WHERE id=? AND status='pending'", [dict(self.PENDING[0], author="Ed Editor")])
        e.fire("weazel:server:approvePending", 4, 9)
        self.assertNotEqual(e.writes("rp_articles"), [])

    def test_nothing_is_ever_posted_to_a_web_hook_even_if_old_convars_are_still_set(self):
        e = env(convars=OLD_HOOKS)
        e.respond("query", "WHERE id=? AND status='pending'", [dict(self.PENDING[0], title="@everyone", content="@here")])
        e.fire("weazel:server:approvePending", 4, 9)
        self.assertEqual(e.http, [])
        self.assertEqual(len(e.sent("weazel:client:articleNotification")), 8)   # players are told in game instead


class StaffActions(unittest.TestCase):
    def test_non_ceo_cannot_use_admin_events(self):
        for src in (1, 2, 3, 4):
            e = env()
            e.fire("weazel:server:setGrade", src, {"citizenid": "REP0", "newGrade": 1})
            e.fire("weazel:server:fire", src, "REP0")
            e.fire("weazel:server:recruit", src, 8)
            e.fire("weazel:server:getJournalists", src)
            self.assertEqual(e.setjobs(), [], src)
            self.assertEqual(e.writes("players"), [], src)
            self.assertEqual(e.sent("weazel:client:setAdmin"), [], src)

    def test_invalid_grades_rejected(self):
        for bad in (99, -1, 1.5, "x", None, 4, True):
            e = env()
            e.fire("weazel:server:setGrade", 5, {"citizenid": "REP0", "newGrade": bad})
            self.assertEqual(e.setjobs(), [], bad)
            self.assertEqual(e.writes("players"), [], bad)

    def test_set_grade_on_online_journalist(self):
        e = env()
        e.fire("weazel:server:setGrade", 5, {"citizenid": "REP0", "newGrade": 2})
        self.assertEqual(e.setjobs(), [(2, "reporter", 2)])

    def test_cannot_touch_non_journalist_online_or_offline(self):
        e = env()
        e.fire("weazel:server:setGrade", 5, {"citizenid": "POL1", "newGrade": 1})
        e.fire("weazel:server:fire", 5, "POL1")
        self.assertEqual(e.setjobs(), [])
        e.respond("query", "SELECT job FROM players", [{"job": job_json("police", 4)}])
        e.fire("weazel:server:setGrade", 5, {"citizenid": "OFFLINE_COP", "newGrade": 0})
        e.fire("weazel:server:fire", 5, "OFFLINE_COP")
        self.assertEqual(e.writes("players"), [])

    def test_offline_journalist_is_updated_with_validated_json(self):
        e = env()
        e.respond("query", "SELECT job FROM players", [{"job": job_json("reporter", 1)}])
        e.fire("weazel:server:setGrade", 5, {"citizenid": "OFFLINE_J", "newGrade": 2})
        updates = [(s, p) for k, s, p in e.sql if k == "update" and "UPDATE players" in s]
        self.assertEqual(len(updates), 1)
        saved = json.loads(updates[0][1][0])
        self.assertEqual((saved["name"], saved["grade"]["level"]), ("reporter", 2))

    def test_no_self_change_and_no_action_on_equal_rank(self):
        e = env()
        e.fire("weazel:server:setGrade", 5, {"citizenid": "CEO1", "newGrade": 0})
        e.fire("weazel:server:fire", 5, "CEO1")
        e.fire("weazel:server:setGrade", 5, {"citizenid": "CEO2", "newGrade": 0})
        e.fire("weazel:server:fire", 5, "CEO2")
        self.assertEqual(e.setjobs(), [])

    def test_fire_journalist(self):
        e = env()
        e.fire("weazel:server:fire", 5, "REP1")
        self.assertEqual(e.setjobs(), [(3, "unemployed", 0)])

    def test_malformed_ids_are_ignored(self):
        e = env()
        for bad in ("x'; DROP TABLE players;--", "", None, 123, {"a": 1}, "a" * 200):
            e.fire("weazel:server:fire", 5, bad)
        self.assertEqual(e.setjobs(), [])
        self.assertEqual(e.writes("players"), [])

    def test_recruit_rules(self):
        e = env()
        e.fire("weazel:server:recruit", 5, 7)  # police officer
        e.fire("weazel:server:recruit", 5, 5)  # self
        e.fire("weazel:server:recruit", 5, 3)  # already a reporter
        e.fire("weazel:server:recruit", 5, 99)  # offline
        e.fire("weazel:server:recruit", 5, "abc")
        self.assertEqual(e.setjobs(), [])
        e.fire("weazel:server:recruit", 5, 8)  # unemployed
        self.assertEqual(e.setjobs(), [(8, "reporter", 0)])


class Content(unittest.TestCase):
    def test_non_reporters_cannot_write(self):
        e = env()
        art = {"title": "T", "content": "C", "category": "crime"}
        e.fire("weazel:server:saveDraft", 1, art)
        e.fire("weazel:server:publishArticle", 1, art)
        e.fire("weazel:server:createDossier", 1, "x")
        e.fire("weazel:server:addEntry", 1, {"id": 1, "status": "rumour", "content": "x"})
        e.fire("weazel:server:getTimeline", 1, 1)
        self.assertEqual(e.writes("rp_"), [])
        self.assertEqual(e.sent("weazel:client:setTimeline"), [])

    def test_article_input_validation(self):
        bad = [
            {"title": "", "content": "C"}, {"title": "T", "content": ""}, {"title": "x" * 121, "content": "C"},
            {"title": "T", "content": "x" * 15001}, {"title": 5, "content": "C"}, {"title": "T", "content": "C", "image": "javascript:alert(1)"},
            {"title": "T", "content": "C", "image": "https://x.test/a'onerror='alert(1)"},
            {"title": "T", "content": "C", "image": "https://x.test/a b"}, {"title": "T", "content": "C", "image": 5},
        ]
        for art in bad:
            e = env()
            e.fire("weazel:server:saveDraft", 3, art)
            self.assertEqual(e.writes("rp_articles"), [], art)

    def test_valid_draft_and_unknown_category_normalised(self):
        e = env()
        e.fire("weazel:server:saveDraft", 3, {"title": " Title ", "content": "Body", "category": "<script>", "image": "https://cdn.test/a.png?x=1&y=2"})
        ins = [p for k, s, p in e.sql if k == "insert" and "INSERT INTO rp_articles" in s]
        self.assertEqual(len(ins), 1)
        self.assertEqual(ins[0][0], "Title")
        self.assertIn("breaking", ins[0])

    def test_intern_cannot_publish_editor_can(self):
        e = env()
        e.fire("weazel:server:publishArticle", 2, {"title": "T", "content": "C"})
        self.assertEqual(e.writes("rp_articles"), [])
        e = env()
        e.fire("weazel:server:publishArticle", 3, {"title": "T", "content": "C"})
        self.assertIn("'pending'", " ".join(s for k, s, p in e.sql) + str([p for k, s, p in e.sql]))
        e = env(convars=OLD_HOOKS)
        e.fire("weazel:server:publishArticle", 4, {"title": "T", "content": "C"})
        self.assertEqual(e.http, [])  # editor publishes directly; players are told in game, nothing goes to Discord
        self.assertTrue(e.sent("weazel:client:articleNotification"))

    def test_publish_draft_saves_form_edits_first(self):
        e = env()
        e.respond("query", "WHERE id=? AND status='draft'", [{"id": 7, "author": "Jo Journalist"}])
        e.fire("weazel:server:publishDraft", 3, {"id": 7, "title": "Edited", "content": "New body", "category": "crime"})
        stmts = [s for s in e.writes("rp_articles")]
        self.assertEqual(len(stmts), 2)
        self.assertIn("SET title=?", stmts[0])
        self.assertIn("status='pending'", stmts[1])

    def test_ownership_by_citizenid_once_migrated(self):
        row = {"id": 7, "author": "Jo Journalist", "author_citizenid": "SOMEONE_ELSE"}
        for has_cid, expect_write in ((False, True), (True, False)):
            e = env(has_author_cid=has_cid)
            e.respond("query", "WHERE id=? AND status='draft'", [row])
            e.fire("weazel:server:updateDraft", 3, {"id": 7, "title": "T", "content": "C"})
            self.assertEqual(any("SET title=?" in s for s in e.writes("rp_articles")), expect_write, has_cid)

    def test_timeline_entries(self):
        e = env()
        e.respond("query", "FROM rp_dossiers WHERE id=?", [{"id": 1}])
        e.fire("weazel:server:addEntry", 2, {"id": 1, "status": "confirmed", "content": "x"})  # intern: rumour only
        e.fire("weazel:server:addEntry", 3, {"id": 1, "status": "weird", "content": "x"})
        e.fire("weazel:server:addEntry", 3, {"id": 1, "status": "rumour", "content": ""})
        self.assertEqual(e.writes("rp_dossier_entries"), [])
        e.fire("weazel:server:addEntry", 2, {"id": 1, "status": "rumour", "content": "ok"})
        e.fire("weazel:server:addEntry", 3, {"id": 1, "status": "confirmed", "content": "ok"})
        self.assertEqual(len(e.writes("INSERT INTO rp_dossier_entries")), 2)

    def test_entry_edits_need_editor_and_valid_type(self):
        e = env()
        e.respond("query", "FROM rp_dossier_entries WHERE id=?", [{"dossier_id": 1}])
        e.fire("weazel:server:changeEntryType", 3, {"entryId": 1, "newType": "confirmed"})
        e.fire("weazel:server:changeEntryType", 4, {"entryId": 1, "newType": "pwned"})
        e.fire("weazel:server:deleteEntry", 3, 1)
        self.assertEqual(e.writes("rp_dossier_entries"), [])
        e.fire("weazel:server:changeEntryType", 4, {"entryId": 1, "newType": "denied"})
        self.assertEqual(len(e.writes("UPDATE rp_dossier_entries")), 1)


class LikesAndComments(unittest.TestCase):
    def published(self, e):
        e.respond("query", "SELECT title FROM rp_articles", [{"title": "T"}])

    def test_like_broadcast_does_not_leak_liker_state(self):
        e = env()
        self.published(e)
        e.respond("update", "DELETE FROM article_likes", 0)  # no existing like: this click adds one
        e.fire("weazel:server:likeArticle", 3, 5)
        everyone = e.sent("weazel:client:updateLikes", -1)[0][1]
        self.assertNotIn("liked", everyone)
        mine = e.sent("weazel:client:updateLikes", 3)[0][1]
        self.assertTrue(mine["liked"])

    def test_unlike_when_row_removed(self):
        e = env()
        self.published(e)
        e.respond("update", "DELETE FROM article_likes", 1)
        e.fire("weazel:server:likeArticle", 3, 5)
        self.assertFalse(e.sent("weazel:client:updateLikes", 3)[0][1]["liked"])
        self.assertEqual(e.writes("INSERT"), [])

    def test_cannot_like_or_comment_unpublished(self):
        e = env()  # title lookup returns nothing
        e.fire("weazel:server:likeArticle", 3, 5)
        e.fire("weazel:server:addComment", 3, {"articleId": 5, "comment": "hi"})
        self.assertEqual(e.writes("article_"), [])

    def test_comment_length_enforced_server_side(self):
        e = env()
        self.published(e)
        e.fire("weazel:server:addComment", 3, {"articleId": 5, "comment": "x" * 151})
        e.fire("weazel:server:addComment", 3, {"articleId": 5, "comment": "   "})
        e.fire("weazel:server:addComment", 3, {"articleId": 5, "comment": 5})
        self.assertEqual(e.writes("article_comments"), [])
        e.fire("weazel:server:addComment", 3, {"articleId": 5, "comment": "x" * 150})
        self.assertEqual(len(e.writes("INSERT INTO article_comments")), 1)

    def test_comment_rate_limit(self):
        e = env()
        self.published(e)
        for _ in range(8):
            e.fire("weazel:server:addComment", 1, {"articleId": 5, "comment": "spam"})
        self.assertEqual(len(e.writes("INSERT INTO article_comments")), 4)

    def test_comment_delete_rules(self):
        e = env()
        e.respond("query", "SELECT article_id, citizenid FROM article_comments", [{"article_id": 5, "citizenid": "CIT1"}])
        e.fire("weazel:server:deleteComment", 8, 1)  # other citizen
        e.fire("weazel:server:deleteComment", 3, 1)  # journalist (below editor)
        self.assertEqual(e.writes("DELETE FROM article_comments"), [])
        e.fire("weazel:server:deleteComment", 1, 1)  # owner
        e.fire("weazel:server:deleteComment", 4, 1)  # editor
        self.assertEqual(len(e.writes("DELETE FROM article_comments")), 2)

    def test_burst_of_likes_does_not_rebroadcast_every_article_each_time(self):
        e = env()
        self.published(e)
        for src in (1, 2, 3, 4):
            e.fire("weazel:server:likeArticle", src, 5)
        self.assertEqual(len(e.timeouts), 1)  # one queued refresh
        self.assertEqual(e.sent("weazel:client:setLatestNews"), [])


class RepoHygiene(unittest.TestCase):
    def test_no_webhook_urls_or_tokens_in_source(self):
        pat = re.compile(r"discord(app)?\.com/api/webhooks/\d+/[\w-]+")
        for base, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules")]
            for f in files:
                if f.endswith((".lua", ".js", ".html", ".md", ".sql", ".cfg", ".txt")):
                    if f == "phase-1-audit.md":
                        continue
                    with open(os.path.join(base, f), encoding="utf-8", errors="ignore") as fh:
                        text = fh.read()
                    self.assertIsNone(pat.search(text), os.path.join(base, f))

    def test_ui_has_no_unsafe_html_sinks_with_data(self):
        with open(os.path.join(ROOT, "html", "script.js"), encoding="utf-8") as f:
            js = f.read()
        for line in js.splitlines():
            if "innerHTML" in line and "=" in line:
                self.assertTrue(re.search(r'innerHTML\s*=\s*("[^"$`]*"|\'[^\'$`]*\');?\s*$', line.strip()) or line.strip().endswith('= "";'), line)
        with open(os.path.join(ROOT, "html", "index.html"), encoding="utf-8") as f:
            self.assertNotIn("onclick=", f.read())


if __name__ == "__main__":
    unittest.main()
