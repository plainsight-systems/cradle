+++
title = 'About the series'
description = 'Why I’m building a transformer inference engine in C#, and what I owe to Jack Crenshaw’s approach to teaching.'
+++

I want to build a transformer inference engine with .NET developers, in a language they already use, and explain the code as we write it. That is the purpose of **Let’s Build a Transformer!** We will start with an empty C# program and extend it until it can load a trained model and generate text. The program is called **Cradle**.

There is a particular kind of understanding I want us to get out of this. When the model produces a token, we should be able to follow the work that produced it: which values went into a calculation, where the weights came from, what ran on the GPU, and how the result became the next input. Writing those operations ourselves gives us something we can inspect, change, and check.

## What I owe to Crenshaw

I learned top-down recursive-descent parsing from Jack Crenshaw’s [Let’s Build a Compiler!](https://compilers.iecc.com/crenshaw/). I used it many times afterward, including in a custom color formatter I wrote for a C board that didn’t have one. His series gave me a technique I could take into another program and use.

Crenshaw taught by having the reader build and run things. He introduced a piece of the compiler, kept the implementation small enough to follow, and showed how to extend it. He made simplifying assumptions explicit. You could try an input, see what the program did, and have a reason to understand the next change.

That is the approach I want to carry into this series. A transformer has different machinery, but we can still introduce it through small additions to a working program. We can start with values we can check ourselves, explain why an operation is needed, and keep using it as the program grows.

Both names are deliberate homages. **Let’s Build a Transformer!** borrows the invitation, including the exclamation mark. **Cradle** was Crenshaw’s name for his starter program. It seems a fitting name for the program we will grow here.

## Why C#, and why the GPU from the start?

The .NET community is the audience I want to write for. So much of the material about building and running these models assumes Python. I want a C# developer to be able to work through inference without first changing languages, and to reach the calculations underneath the framework calls.

We will write the GPU kernels in C#, using ILGPU. A kernel is a function that runs on the GPU; the arithmetic and indexing inside it will be ours to implement. That matters to the explanation. When we multiply matrices, we should be able to open the kernel and follow how it reads a row, reads a column, and accumulates the result.

The first installment will put two arrays on the GPU, add them, and check the values we get back. That gives us the beginnings of the execution path we will keep using. GPU buffers and kernel launches become part of the program before we ask them to carry a transformer. File loading, tokenization, and the code that coordinates those operations will run on the CPU.

We want .NET developers to be able to follow along on Windows, Linux, and Mac. Choosing C# to reach this community means including the different systems people use, and support for all three is part of the goal.

Mac takes some extra care. Our tested setup uses a development build of ILGPU to run the C# kernels through Metal, Apple’s GPU programming interface, along with a few workarounds in the code. We will explain those where they matter and document the tested platforms, GPU requirements, and exact versions needed to follow along.

## One program, all the way through

Every installment must leave the cradle with a new capability we can run. Matrix multiplication stays in the program when attention arrives. Attention becomes part of a transformer block. The block becomes part of the full model. The small examples stay with us as checks when we replace deliberately chosen weights with weights from a trained model.

We will use those checks to give the explanations some teeth. A plausible number is not enough to establish that a GPU kernel is correct. For small inputs, we can calculate an expected result independently and compare it with what the kernel returns. As the program grows, we can compare larger pieces against an independent reference.

We will follow Crenshaw’s method here: build a small piece, run it, and understand what it does before extending it. You need to be comfortable programming in C#. You do not need to have studied machine learning or worked through a textbook on linear algebra before starting. We will introduce the GPU concepts and the math when the code needs them, using small examples we can follow together.

We will stay out of extended theory and introduce only the math required to understand the pieces we are writing. For a matrix multiplication, that means following which values we multiply and add, and how those values produce one element of the result. When a calculation overflows, we will explain the change that fixes it and check that it preserves the result we wanted. Each explanation has a job in the program we have in front of us.

That also means we will open up the functions we use. Calling an attention function and moving on would leave the interesting part unexplained. We will write its operations, inspect their inputs and outputs, and show how they fit together. By the time we give a piece of code a name and reuse it, we should know what work that name stands for.

The goal is an understandable inference engine that runs real model weights. We will use a model that has already been trained. We will get text generation working, then add a cache to reuse earlier calculations, sampling to vary token selection, and support for quantized weights. Performance work comes after we have a working implementation we understand and can measure. A production runtime has a much wider set of obligations than this series can take on.

## Following along

The series is in preparation. When lessons are published, each will include links to the code at its starting and completed stages. Those snapshots will remain available as the main program moves forward. Setup instructions will accompany the first lesson, including the tested .NET and ILGPU versions and GPU requirements.

The [series index]({{< relref "/lessons" >}}) shows the planned route and distinguishes published lessons from work still ahead. The sequence can change as we write and build. Full articles will appear here and on [andrewphunter.com](https://andrewphunter.com/), with both editions coming from the same source.

## A little about me

I’m a systems architect and builder. My route here came through the Navy’s nuclear power program, where I learned technical writing through operating policies and procedures. Explaining how a system behaves to someone who has to operate it gives you a fairly concrete reason to get the explanation right. I carried that habit into software, and into the way I write about it.

At [Plainsight Systems](https://plainsight-systems.com/about/), I build things to work through questions that interest me. Charlotte is an inference engine for the browser. In [Serenity](https://github.com/plainsight-systems/serenity), I’m approaching GPU performance from the rendering side, exploring techniques that also matter to transformer inference: processing data in small pieces, keeping a small amount of running state, and combining partial results or reusing earlier work. Its moving lights give me a way to investigate those techniques with an image at the end, where people can see what the kernel work makes possible.

Those connections are part of what keeps me interested. A question about a tokenizer sent me back to Claude Shannon’s 1948 paper; rendering gives me another way into the machinery behind inference.

Cradle gives me a way to work through one of those builds with you, explaining the decisions as the program takes shape. My [other writing](https://andrewphunter.com/) covers software architecture, delivery, and AI, with the same interest in why a system behaves the way it does.

The code is licensed under [Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0). The writing is copyright Andrew P Hunter, licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
