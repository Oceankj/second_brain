-- Keep enum additions in their own committed migration before use.
alter type memory_link_type add value if not exists 'replies_to';
alter type memory_link_type add value if not exists 'derived_from';
