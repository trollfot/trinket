Granite
=======

Chiseled for duration

Acknowledgments
---------------

Granite's Request, Response, Parsers and HTTP entities (Query, MultiPart...) are based on Roll's code.
See : https://github.com/pyrates/roll

It was tuned and modified very slightly to accomodate my ideas: a new workflow for the request/response and the streaming of the request's body at the handler's leisure.

Compared to my Roll's fork, the whole upgrade and websockets parts were re-written with a new library, 'wsproto'.

Why ?
-----

I like Curio's async concepts, syntax and philosophy.
The performances were not a focus on this proof of concept, but they are on par with Roll on asyncio.

What now ?
----------

A lot of tests to write. Performances to enhance. Have a look at http2 using h2.
