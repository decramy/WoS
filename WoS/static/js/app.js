document.addEventListener('DOMContentLoaded', function () {
	// Theme initialization: respect saved preference or OS preference
	// helper that safely accesses localStorage (may throw in some privacy modes)
	function lsGet(key) {
		try { return localStorage.getItem(key); } catch (e) { return null; }
	}
	function lsSet(key, val) {
		try { localStorage.setItem(key, val); return true; } catch (e) { return false; }
	}

	try {
		var saved = lsGet('wos-theme'); // 'auto'|'dark'|'light'|null
		var prefersDarkMQ = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)');
		var prefersDark = prefersDarkMQ ? prefersDarkMQ.matches : false;

		function setBodyClassFor(name) {
			var body = document.body;
			body.classList.remove('dark', 'light');
			if (name === 'dark') body.classList.add('dark');
			else if (name === 'light') body.classList.add('light');
		}

		function applyTheme(name) {
			// name can be 'auto'|'dark'|'light'
			var actual = name;
			if (name === 'auto') {
				actual = (prefersDarkMQ && prefersDarkMQ.matches) ? 'dark' : 'light';
			}
			setBodyClassFor(actual);
			// update toggle icon and title
			var btn = document.getElementById('theme-toggle');
			if (btn) {
				if (name === 'auto') {
					btn.textContent = 'A';
					btn.title = 'Theme: Auto (follows OS)';
				} else if (name === 'dark') {
					btn.textContent = '🌙';
					btn.title = 'Theme: Dark';
				} else {
					btn.textContent = '☀️';
					btn.title = 'Theme: Light';
				}
			}
		}

		var initial = 'auto';
		if (saved === 'dark' || saved === 'light' || saved === 'auto') initial = saved;
		else initial = prefersDark ? 'dark' : 'light';
		applyTheme(initial);

		// cycle order: auto -> dark -> light -> auto
		var themeToggle = document.getElementById('theme-toggle');
		if (themeToggle) {
			themeToggle.addEventListener('click', function () {
				var current = lsGet('wos-theme');
				if (!current) {
					current = document.body.classList.contains('dark') ? 'dark' : 'light';
					if (saved === null) current = 'auto';
				}
				var order = ['auto', 'dark', 'light'];
				var idx = order.indexOf(current);
				if (idx === -1) idx = 0;
				var next = order[(idx + 1) % order.length];
				lsSet('wos-theme', next);
				applyTheme(next);
			});
		}
		// if OS preference changes, and user is in 'auto', reapply
		if (prefersDarkMQ && typeof prefersDarkMQ.addEventListener === 'function') {
			prefersDarkMQ.addEventListener('change', function () {
				var cur = lsGet('wos-theme') || 'auto';
				if (cur === 'auto') applyTheme('auto');
			});
		}
	} catch (e) {
		console.warn('theme init error', e);
		// fall back: ensure toggle still works using in-memory state
		var themeToggle = document.getElementById('theme-toggle');
		if (themeToggle) {
			themeToggle.addEventListener('click', function () {
				var body = document.body;
				var isDark = body.classList.contains('dark');
				if (isDark) {
					body.classList.remove('dark');
					body.classList.add('light');
					themeToggle.textContent = '☀️';
					themeToggle.title = 'Theme: Light (no storage)';
				} else {
					body.classList.remove('light');
					body.classList.add('dark');
					themeToggle.textContent = '🌙';
					themeToggle.title = 'Theme: Dark (no storage)';
				}
			});
		}
	}
		var toggle = document.getElementById('toggle-epic-form');
	var epicCreate = document.getElementById('epic-create');
	var cancel = document.getElementById('cancel-epic-create');
		// header add-epic button removed: header now links to overview pages
	if (toggle && epicCreate) {
		toggle.addEventListener('click', function () {
			if (epicCreate.style.display === 'none' || epicCreate.style.display === '') {
				epicCreate.style.display = 'block';
				var first = epicCreate.querySelector('input[name="title"]');
				if (first) first.focus();
			} else {
				epicCreate.style.display = 'none';
			}
		});
	}

	if (cancel && epicCreate) {
		cancel.addEventListener('click', function () {
			epicCreate.style.display = 'none';
		});
	}

	// Escape hides the epic form
	document.addEventListener('keydown', function (ev) {
		if (ev.key === 'Escape' && epicCreate && epicCreate.style.display === 'block') {
			epicCreate.style.display = 'none';
		}
	});

	// open epic create form when the URL contains #epic-create or ?show_epic_form=1
	try {
		var url = new URL(window.location.href);
		if (url.hash === '#epic-create' || url.searchParams.get('show_epic_form') === '1') {
			if (epicCreate) {
				epicCreate.style.display = 'block';
				var first = epicCreate.querySelector('input[name="title"]');
				if (first) first.focus();
			}
		}
	} catch (e) {
		// ignore
	}
});